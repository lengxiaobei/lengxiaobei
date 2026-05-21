use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Mutex;
use warp::Filter;
use std::path::Path;
use log::{info, warn, error};
use simple_logger::SimpleLogger;

#[derive(Serialize, Deserialize, Debug, Clone)]
struct Memory {
    id: u64,
    content: String,
    memory_type: String,
    timestamp: u64,
    embedding: Vec<f32>,
}

#[derive(Serialize, Deserialize)]
struct MemoryRequest {
    content: String,
    memory_type: String,
}

#[derive(Serialize, Deserialize)]
struct SearchRequest {
    query: String,
    limit: Option<usize>,
    memory_type: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct SearchResult {
    id: u64,
    content: String,
    memory_type: String,
    distance: f32,
    timestamp: u64,
}

struct MemoryManager {
    memories: Vec<Memory>,
    next_id: u64,
}

impl MemoryManager {
    fn new() -> Self {
        Self {
            memories: Vec::new(),
            next_id: 0,
        }
    }

    // 生成简单的文本嵌入（基于字符频率）
    fn generate_embedding(&self, text: &str) -> Vec<f32> {
        let mut embedding = vec![0.0; 256]; // 256维向量
        
        // 计算字符频率
        for c in text.chars() {
            let code = c as u8;
            embedding[code as usize] += 1.0;
        }
        
        // 归一化
        let norm: f32 = embedding.iter().map(|&x| x * x).sum::<f32>().sqrt();
        if norm > 0.0 {
            for x in &mut embedding {
                *x /= norm;
            }
        }
        
        embedding
    }

    // 计算余弦相似度
    fn cosine_similarity(&self, vec1: &[f32], vec2: &[f32]) -> f32 {
        let mut dot_product = 0.0;
        let mut norm1 = 0.0;
        let mut norm2 = 0.0;
        
        for (a, b) in vec1.iter().zip(vec2.iter()) {
            dot_product += a * b;
            norm1 += a * a;
            norm2 += b * b;
        }
        
        if norm1 > 0.0 && norm2 > 0.0 {
            dot_product / (norm1.sqrt() * norm2.sqrt())
        } else {
            0.0
        }
    }

    fn add_memory(&mut self, content: String, memory_type: String) -> u64 {
        let embedding = self.generate_embedding(&content);
        
        let memory = Memory {
            id: self.next_id,
            content,
            memory_type,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
            embedding,
        };

        self.memories.push(memory);

        let id = self.next_id;
        self.next_id += 1;
        id
    }

    fn search_memories(&self, query: &str, limit: usize, memory_type: Option<&str>) -> Vec<SearchResult> {
        let query_embedding = self.generate_embedding(query);
        
        let mut results: Vec<SearchResult> = self.memories
            .iter()
            .filter(|mem| {
                if let Some(memory_type) = memory_type {
                    mem.memory_type == memory_type
                } else {
                    true
                }
            })
            .map(|mem| {
                let similarity = self.cosine_similarity(&query_embedding, &mem.embedding);
                let distance = 1.0 - similarity; // 转换为距离
                
                SearchResult {
                    id: mem.id,
                    content: mem.content.clone(),
                    memory_type: mem.memory_type.clone(),
                    distance,
                    timestamp: mem.timestamp,
                }
            })
            .collect();
        
        // 按距离排序
        results.sort_by(|a, b| a.distance.partial_cmp(&b.distance).unwrap());
        
        // 取前limit个结果
        results.truncate(limit);
        results
    }

    fn save_to_file(&self, path: &str) -> Result<(), String> {
        let data = serde_json::to_string(&self.memories)
            .map_err(|e| format!("序列化失败: {}", e))?;
        std::fs::write(path, data)
            .map_err(|e| format!("写入文件失败: {}", e))?;
        Ok(())
    }

    fn load_from_file(&mut self, path: &str) -> Result<(), String> {
        if Path::new(path).exists() {
            let data = std::fs::read_to_string(path)
                .map_err(|e| format!("读取文件失败: {}", e))?;
            
            // 尝试解析旧格式（没有embedding字段）
            #[derive(Deserialize)]
            struct OldMemory {
                id: u64,
                content: String,
                memory_type: String,
                timestamp: u64,
            }
            
            match serde_json::from_str::<Vec<OldMemory>>(&data) {
                Ok(old_memories) => {
                    // 转换旧格式到新格式
                    self.memories = old_memories.into_iter().map(|old| {
                        let embedding = self.generate_embedding(&old.content);
                        Memory {
                            id: old.id,
                            content: old.content,
                            memory_type: old.memory_type,
                            timestamp: old.timestamp,
                            embedding,
                        }
                    }).collect();
                    self.next_id = self.memories.last().map(|m| m.id + 1).unwrap_or(0);
                },
                Err(_) => {
                    // 尝试解析新格式
                    self.memories = serde_json::from_str(&data)
                        .map_err(|e| format!("反序列化失败: {}", e))?;
                    self.next_id = self.memories.last().map(|m| m.id + 1).unwrap_or(0);
                }
            }
        }
        Ok(())
    }
}

#[tokio::main]
async fn main() {
    // 初始化日志
    SimpleLogger::new()
        .with_level(log::LevelFilter::Info)
        .init()
        .unwrap();

    info!("正在启动记忆层服务...");

    let memory_manager = Arc::new(Mutex::new(MemoryManager::new()));

    // 加载记忆
    {
        let mut manager = memory_manager.lock().await;
        match manager.load_from_file("memories.json") {
            Ok(_) => info!("成功加载记忆"),
            Err(e) => warn!("加载记忆失败: {}", e),
        }
    }

    // 定期保存记忆的后台任务
    let manager_clone = memory_manager.clone();
    tokio::spawn(async move {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(5 * 60)).await;
            let manager = manager_clone.lock().await;
            match manager.save_to_file("memories.json") {
                Ok(_) => info!("成功保存记忆"),
                Err(e) => error!("保存记忆失败: {}", e),
            }
        }
    });

    // 添加记忆的路由
    let memory_manager_add = memory_manager.clone();
    let add_route = warp::path!("api" / "memory" / "add")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(move |req: MemoryRequest| {
            let memory_manager = memory_manager_add.clone();
            async move {
                info!("接收到添加记忆请求: type={}", req.memory_type);
                let mut manager = memory_manager.lock().await;
                let id = manager.add_memory(req.content, req.memory_type);
                info!("成功添加记忆，ID: {}", id);
                let response = serde_json::json!({
                    "status": "success",
                    "id": id
                });
                Ok::<_, warp::Rejection>(warp::reply::json(&response))
            }
        });

    // 搜索记忆的路由
    let memory_manager_search = memory_manager.clone();
    let search_route = warp::path!("api" / "memory" / "search")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(move |req: SearchRequest| {
            let memory_manager = memory_manager_search.clone();
            async move {
                info!("接收到搜索记忆请求: query={}, limit={:?}, type={:?}", 
                      req.query, req.limit, req.memory_type);
                let manager = memory_manager.lock().await;
                let limit = req.limit.unwrap_or(5);
                let results = manager.search_memories(
                    &req.query,
                    limit,
                    req.memory_type.as_deref()
                );
                info!("搜索完成，找到 {} 条记忆", results.len());
                let response = serde_json::json!({
                    "status": "success",
                    "results": results
                });
                Ok::<_, warp::Rejection>(warp::reply::json(&response))
            }
        });

    let routes = add_route.or(search_route);

    info!("记忆层服务启动在 http://localhost:8081");
    warp::serve(routes)
        .run(([127, 0, 0, 1], 8081))
        .await;
}
