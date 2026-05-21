use std::process::{Command, Stdio}; use std::time::Duration; use tokio::time; use serde::{Deserialize, Serialize}; use std::fs::File; use std::io::{Read, Write}; use std::sync::Arc; use tokio::sync::Mutex; use warp::Filter; use serde_json::Value; use log::{info, warn, error}; use simple_logger::SimpleLogger; use sysinfo::{System, Cpu}; use reqwest::Client;

#[derive(Serialize, Deserialize)]
struct AgentState {
    goals: Vec<serde_json::Value>,
    motivations: Vec<serde_json::Value>,
    memory: Vec<serde_json::Value>,
    last_action: String,
}

#[derive(Serialize, Deserialize)]
struct UpdateRequest {
    code_path: String,
    new_code: String,
}

#[derive(Serialize, Deserialize)]
struct StatusResponse {
    status: String,
    python_pid: Option<u32>,
    uptime: u64,
    memory_usage: f64,
    cpu_usage: f64,
    memory_service_status: String,
}

#[derive(Serialize, Deserialize)]
struct MemoryRequest {
    content: String,
    memory_type: String,
}

#[derive(Serialize, Deserialize)]
struct MemoryResponse {
    status: String,
    id: u64,
}

struct AgentManager {
    python_process: Option<std::process::Child>,
    state: AgentState,
    start_time: std::time::Instant,
    http_client: Client,
}

impl AgentManager {
    fn new() -> Self {
        Self {
            python_process: None,
            state: AgentState {
                goals: Vec::new(),
                motivations: Vec::new(),
                memory: Vec::new(),
                last_action: String::new(),
            },
            start_time: std::time::Instant::now(),
            http_client: Client::new(),
        }
    }
    
    fn start_python(&mut self) -> Result<(), String> {
        info!("启动Python核心进程...");
        // 使用-m参数以模块方式运行，这样可以正确处理相对导入
        let mut cmd = Command::new("python3");
        let project_dir = std::env::var("LENGXIAOBEI_ROOT")
            .unwrap_or_else(|_| {
                let cwd = std::env::current_dir()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_else(|_| ".".to_string());
                let parent = std::path::Path::new(&cwd)
                    .parent()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or(cwd);
                parent
            });
        cmd.arg("-m")
            .arg("src.core")
            .current_dir(&project_dir)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        
        let process = cmd.spawn()
            .map_err(|e| format!("启动Python进程失败: {}", e))?;
        
        self.python_process = Some(process);
        info!("Python核心进程启动成功，PID: {:?}", self.python_process.as_ref().unwrap().id());
        Ok(())
    }
    
    fn stop_python(&mut self) {
        if let Some(mut process) = self.python_process.take() {
            info!("停止Python核心进程...");
            match process.kill() {
                Ok(_) => info!("Python核心进程已停止"),
                Err(e) => error!("停止Python核心进程失败: {}", e),
            }
            let _ = process.wait();
        }
    }
    
    fn save_state(&self) -> Result<(), String> {
        let state_json = serde_json::to_string(&self.state)
            .map_err(|e| format!("序列化状态失败: {}", e))?;
        
        let mut file = File::create("agent_state.json")
            .map_err(|e| format!("创建状态文件失败: {}", e))?;
        
        file.write_all(state_json.as_bytes())
            .map_err(|e| format!("写入状态文件失败: {}", e))?;
        
        info!("状态已保存");
        Ok(())
    }
    
    fn load_state(&mut self) -> Result<(), String> {
        if let Ok(mut file) = File::open("agent_state.json") {
            let mut state_json = String::new();
            file.read_to_string(&mut state_json)
                .map_err(|e| format!("读取状态文件失败: {}", e))?;
            
            self.state = serde_json::from_str(&state_json)
                .map_err(|e| format!("反序列化状态失败: {}", e))?;
            
            info!("状态已加载");
        } else {
            info!("状态文件不存在，使用默认状态");
        }
        Ok(())
    }
    
    async fn check_memory_service(&self) -> String {
        match self.http_client.post("http://localhost:8081/api/memory/search")
            .json(&serde_json::json!({
                "query": "test",
                "limit": 1
            }))
            .send()
            .await {
            Ok(response) if response.status().is_success() => "running".to_string(),
            _ => "not_running".to_string(),
        }
    }
    
    async fn add_memory(&self, content: String, memory_type: String) -> Result<u64, String> {
        let response = self.http_client.post("http://localhost:8081/api/memory/add")
            .json(&MemoryRequest {
                content,
                memory_type,
            })
            .send()
            .await
            .map_err(|e| format!("调用内存服务失败: {}", e))?;
        
        let memory_response: MemoryResponse = response.json()
            .await
            .map_err(|e| format!("解析内存服务响应失败: {}", e))?;
        
        Ok(memory_response.id)
    }
    
    async fn get_status(&self) -> StatusResponse {
        let uptime = self.start_time.elapsed().as_secs();
        let python_pid = self.python_process.as_ref().map(|p| p.id());
        
        // 获取真实的内存和CPU使用率
        let mut sys = System::new_all();
        sys.refresh_all();
        
        // 计算内存使用率
        let total_memory = sys.total_memory() as f64;
        let used_memory = sys.used_memory() as f64;
        let memory_usage = (used_memory / total_memory) * 100.0;
        
        // 计算CPU使用率
        let cpu_usage = sys.cpus().iter().map(|cpu| cpu.cpu_usage()).sum::<f32>() / sys.cpus().len() as f32;
        
        // 检查内存服务状态
        let memory_service_status = self.check_memory_service().await;
        
        StatusResponse {
            status: "running".to_string(),
            python_pid,
            uptime,
            memory_usage,
            cpu_usage: cpu_usage as f64,
            memory_service_status,
        }
    }
}

#[tokio::main]
async fn main() {
    // 初始化日志
    SimpleLogger::new()
        .with_level(log::LevelFilter::Info)
        .init()
        .unwrap();

    info!("正在启动控制层服务...");

    let agent_manager = Arc::new(Mutex::new(AgentManager::new()));
    
    // 加载状态
    {
        let mut manager = agent_manager.lock().await;
        match manager.load_state() {
            Ok(_) => info!("状态加载完成"),
            Err(e) => warn!("加载状态失败: {}", e),
        }
    }
    
    // 启动Python核心进程
    {
        let mut manager = agent_manager.lock().await;
        match manager.start_python() {
            Ok(_) => info!("Python核心进程启动完成"),
            Err(e) => error!("启动Python核心进程失败: {}", e),
        }
    }
    
    // 监控循环
    let manager_clone = agent_manager.clone();
    tokio::spawn(async move {
        loop {
            {
                let mut manager = manager_clone.lock().await;
                
                // 检查Python进程是否还在运行
                if let Some(process) = &mut manager.python_process {
                    match process.try_wait() {
                        Ok(Some(status)) => {
                            warn!("Python进程退出，状态: {:?}", status);
                            // 重启Python进程
                            if let Err(e) = manager.start_python() {
                                error!("重启Python进程失败: {}", e);
                            }
                        },
                        Ok(None) => {
                            // 进程仍在运行，定期保存状态
                            if let Err(e) = manager.save_state() {
                                warn!("保存状态失败: {}", e);
                            }
                        },
                        Err(e) => {
                            warn!("检查Python进程失败: {}", e);
                        }
                    }
                } else {
                    // Python进程不存在，启动它
                    if let Err(e) = manager.start_python() {
                        error!("启动Python进程失败: {}", e);
                    }
                }
            }
            
            // 等待一段时间后再次检查
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
        }
    });
    
    // 设置HTTP服务器
    let agent_manager_clone1 = agent_manager.clone();
    let status_route = warp::path!("api" / "status")
        .and(warp::get())
        .and_then(move || {
            let agent_manager = agent_manager_clone1.clone();
            async move {
                let manager = agent_manager.lock().await;
                let status = manager.get_status().await;
                Ok::<_, warp::Rejection>(warp::reply::json(&status))
            }
        });
    
    let update_route = warp::path!("api" / "update")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(move |req: UpdateRequest| {
            async move {
                info!("接收到代码更新请求: path={}", req.code_path);
                // 这里应该实现代码更新逻辑
                // 暂时只返回成功
                let response = serde_json::json!({
                    "status": "success", 
                    "message": "代码更新请求已接收"
                });
                Ok::<_, warp::Rejection>(warp::reply::json(&response))
            }
        });
    
    let agent_manager_clone2 = agent_manager.clone();
    let memory_route = warp::path!("api" / "memory" / "add")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(move |req: MemoryRequest| {
            let agent_manager = agent_manager_clone2.clone();
            async move {
                info!("接收到添加记忆请求: type={}", req.memory_type);
                let manager = agent_manager.lock().await;
                match manager.add_memory(req.content, req.memory_type).await {
                    Ok(id) => {
                        let response = serde_json::json!({
                            "status": "success",
                            "id": id
                        });
                        Ok::<_, warp::Rejection>(warp::reply::json(&response))
                    },
                    Err(e) => {
                        let response = serde_json::json!({
                            "status": "error",
                            "message": e
                        });
                        Ok::<_, warp::Rejection>(warp::reply::json(&response))
                    }
                }
            }
        });
    
    let routes = status_route.or(update_route).or(memory_route);
    
    info!("控制层服务启动在 http://localhost:8082");
    warp::serve(routes)
        .run(([127, 0, 0, 1], 8082))
        .await;
}
