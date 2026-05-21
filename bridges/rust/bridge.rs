use std::collections::HashMap;
use std::process::{Child, Command};
use std::sync::Arc;
use tokio::sync::Mutex;

pub enum SpawnMode {
    SingleSession,
    SameDir,
    Worktree,
}

impl std::fmt::Display for SpawnMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SpawnMode::SingleSession => write!(f, "single-session"),
            SpawnMode::SameDir => write!(f, "same-dir"),
            SpawnMode::Worktree => write!(f, "worktree"),
        }
    }
}

pub enum SessionStatus {
    Active,
    Completed,
    Failed,
    Interrupted,
}

impl std::fmt::Display for SessionStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SessionStatus::Active => write!(f, "active"),
            SessionStatus::Completed => write!(f, "completed"),
            SessionStatus::Failed => write!(f, "failed"),
            SessionStatus::Interrupted => write!(f, "interrupted"),
        }
    }
}

pub struct BridgeConfig {
    pub api_base_url: String,
    pub session_ingress_url: String,
    pub dir: String,
    pub max_sessions: usize,
    pub spawn_mode: SpawnMode,
    pub session_timeout_ms: Option<u64>,
    pub debug_file: Option<String>,
    pub verbose: bool,
}

impl BridgeConfig {
    pub fn new(
        api_base_url: String,
        session_ingress_url: String,
        dir: String,
        max_sessions: usize,
        spawn_mode: SpawnMode,
        session_timeout_ms: Option<u64>,
        debug_file: Option<String>,
        verbose: bool,
    ) -> Self {
        Self {
            api_base_url,
            session_ingress_url,
            dir,
            max_sessions,
            spawn_mode,
            session_timeout_ms,
            debug_file,
            verbose,
        }
    }
}

pub fn create_bridge_config(
    api_base_url: String,
    session_ingress_url: String,
    dir: String,
    max_sessions: usize,
    spawn_mode: SpawnMode,
) -> BridgeConfig {
    BridgeConfig::new(
        api_base_url,
        session_ingress_url,
        dir,
        max_sessions,
        spawn_mode,
        Some(3600000), // 默认超时时间
        None,
        false,
    )
}

pub struct SessionHandle {
    pub session_id: String,
    pub process: Child,
    pub current_activity: HashMap<String, serde_json::Value>,
    pub activities: Vec<HashMap<String, serde_json::Value>>,
    pub last_stderr: Vec<String>,
    pub access_token: Option<String>,
}

impl SessionHandle {
    pub fn new(
        session_id: String,
        process: Child,
        current_activity: Option<HashMap<String, serde_json::Value>>,
        activities: Option<Vec<HashMap<String, serde_json::Value>>>,
        last_stderr: Option<Vec<String>>,
        access_token: Option<String>,
    ) -> Self {
        Self {
            session_id,
            process,
            current_activity: current_activity.unwrap_or_default(),
            activities: activities.unwrap_or_default(),
            last_stderr: last_stderr.unwrap_or_default(),
            access_token,
        }
    }

    pub fn update_access_token(&mut self, token: String) {
        self.access_token = Some(token);
    }

    pub fn done(&self) -> bool {
        self.process.try_wait().unwrap().is_some()
    }
}

pub type OnFirstUserMessageCallback = Box<dyn Fn(String) + Send>;

pub struct SessionSpawnOpts {
    pub session_id: String,
    pub sdk_url: String,
    pub access_token: String,
    pub use_ccr_v2: bool,
    pub worker_epoch: Option<i64>,
    pub on_first_user_message: Option<OnFirstUserMessageCallback>,
}

impl SessionSpawnOpts {
    pub fn new(
        session_id: String,
        sdk_url: String,
        access_token: String,
        use_ccr_v2: bool,
        worker_epoch: Option<i64>,
        on_first_user_message: Option<OnFirstUserMessageCallback>,
    ) -> Self {
        Self {
            session_id,
            sdk_url,
            access_token,
            use_ccr_v2,
            worker_epoch,
            on_first_user_message,
        }
    }
}

pub struct SessionSpawner;

impl SessionSpawner {
    pub fn new() -> Self {
        Self
    }

    pub fn spawn(&self, opts: SessionSpawnOpts, dir: &str) -> SessionHandle {
        let process = self.create_session_process();
        SessionHandle::new(
            opts.session_id,
            process,
            None,
            None,
            None,
            Some(opts.access_token),
        )
    }

    fn create_session_process(&self) -> Child {
        Command::new("echo")
            .arg("session spawned")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .expect("Failed to start session process")
    }
}

pub fn create_session_spawner() -> SessionSpawner {
    SessionSpawner::new()
}

pub struct BridgeApiClient {
    pub base_url: String,
}

impl BridgeApiClient {
    pub fn new(base_url: String) -> Self {
        Self { base_url }
    }

    pub async fn poll_for_work(
        &self,
        environment_id: &str,
        environment_secret: &str,
        signal: Option<tokio::sync::broadcast::Receiver<()>>,
        reclaim_older_than_ms: i64,
    ) -> Option<HashMap<String, serde_json::Value>> {
        self.perform_polling(environment_id, environment_secret, signal, reclaim_older_than_ms)
            .await
    }

    async fn perform_polling(
        &self,
        _environment_id: &str,
        _environment_secret: &str,
        _signal: Option<tokio::sync::broadcast::Receiver<()>>,
        _reclaim_older_than_ms: i64,
    ) -> Option<HashMap<String, serde_json::Value>> {
        None
    }

    pub async fn acknowledge_work(
        &self,
        environment_id: &str,
        work_id: &str,
        token: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.send_acknowledgment(environment_id, work_id, token).await
    }

    async fn send_acknowledgment(
        &self,
        _environment_id: &str,
        _work_id: &str,
        _token: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }

    pub async fn heartbeat_work(
        &self,
        environment_id: &str,
        work_id: &str,
        token: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.send_heartbeat(environment_id, work_id, token).await
    }

    async fn send_heartbeat(
        &self,
        _environment_id: &str,
        _work_id: &str,
        _token: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }

    pub async fn stop_work(
        &self,
        environment_id: &str,
        work_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.stop_specific_work(environment_id, work_id).await
    }

    async fn stop_specific_work(
        &self,
        _environment_id: &str,
        _work_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }

    pub async fn reconnect_session(
        &self,
        environment_id: &str,
        session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.perform_reconnection(environment_id, session_id).await
    }

    async fn perform_reconnection(
        &self,
        _environment_id: &str,
        _session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }

    pub async fn archive_session(
        &self,
        session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.archive_specific_session(session_id).await
    }

    async fn archive_specific_session(
        &self,
        _session_id: &str,
    ) -> Result<(), Box<dyn std::error::Error>> {
        Ok(())
    }
}

pub fn create_bridge_api_client(base_url: String) -> BridgeApiClient {
    BridgeApiClient::new(base_url)
}

pub struct BridgeLogger {
    sessions: Arc<Mutex<HashMap<String, String>>>,
    active_sessions: usize,
    max_sessions: usize,
    spawn_mode: SpawnMode,
}

impl BridgeLogger {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
            active_sessions: 0,
            max_sessions: 1,
            spawn_mode: SpawnMode::SingleSession,
        }
    }

    pub fn print_banner(&self, config: &BridgeConfig, environment_id: &str) {
        let banner_msg = format!("Bridge started with environment: {}", environment_id);
        println!("{}", banner_msg);
    }

    pub fn log_session_start(&self, session_id: &str, description: &str) {
        let start_msg = format!("Session started: {} - {}", session_id, description);
        println!("{}", start_msg);
    }

    pub fn log_session_complete(&self, session_id: &str, duration_ms: u64) {
        let complete_msg = format!("Session completed: {} - {}ms", session_id, duration_ms);
        println!("{}", complete_msg);
    }

    pub fn log_session_failed(&self, session_id: &str, message: &str) {
        let fail_msg = format!("Session failed: {} - {}", session_id, message);
        println!("{}", fail_msg);
    }

    pub fn log_error(&self, message: &str) {
        let error_msg = format!("Error: {}", message);
        println!("{}", error_msg);
    }

    pub fn log_verbose(&self, message: &str) {
        let verbose_msg = format!("Verbose: {}", message);
        println!("{}", verbose_msg);
    }

    pub fn log_reconnected(&self, disconnected_ms: u64) {
        let reconn_msg = format!("Reconnected after {}ms", disconnected_ms);
        println!("{}", reconn_msg);
    }

    pub fn set_attached(&self, session_id: &str) {
    }

    pub fn update_session_count(&mut self, count: usize, max_count: usize, spawn_mode: SpawnMode) {
        self.active_sessions = count;
        self.max_sessions = max_count;
        self.spawn_mode = spawn_mode;
    }

    pub fn update_idle_status(&self) {
    }

    pub fn update_session_status(
        &self,
        session_id: &str,
        elapsed: &str,
        activity: &HashMap<String, serde_json::Value>,
        trail: &[String],
    ) {
    }

    pub async fn add_session(&self, session_id: String, url: String) {
        let mut sessions = self.sessions.lock().await;
        sessions.insert(session_id, url);
    }

    pub async fn remove_session(&self, session_id: &str) {
        let mut sessions = self.sessions.lock().await;
        sessions.remove(session_id);
    }

    pub fn set_session_title(&self, session_id: &str, title: &str) {
    }

    pub fn update_session_activity(
        &self,
        session_id: &str,
        activity: &HashMap<String, serde_json::Value>,
    ) {
    }

    pub fn refresh_display(&self) {
    }

    pub fn clear_status(&self) {
    }

    pub fn set_debug_log_path(&self, path: &str) {
    }
}

pub fn create_bridge_logger() -> BridgeLogger {
    BridgeLogger::new()
}

pub async fn run_bridge_loop(
    config: BridgeConfig,
    environment_id: String,
    environment_secret: String,
    api: BridgeApiClient,
    spawner: SessionSpawner,
    logger: BridgeLogger,
    signal: Option<tokio::sync::broadcast::Receiver<()>>,
    initial_session_id: Option<String>,
) {
    initialize_bridge(&config, &environment_id, &logger).await;
    start_main_loop(
        config,
        environment_id,
        environment_secret,
        api,
        spawner,
        logger,
        signal,
        initial_session_id,
    )
    .await;
}

async fn initialize_bridge(config: &BridgeConfig, environment_id: &str, logger: &BridgeLogger) {
    logger.print_banner(config, environment_id);
}

async fn start_main_loop(
    config: BridgeConfig,
    environment_id: String,
    environment_secret: String,
    api: BridgeApiClient,
    spawner: SessionSpawner,
    logger: BridgeLogger,
    signal: Option<tokio::sync::broadcast::Receiver<()>>,
    initial_session_id: Option<String>,
) {
    println!("Bridge loop started");
}

pub type BridgeClient = BridgeApiClient;

mod tests {
    use super::*;

    fn test_spawn_mode_display() {
        assert_eq!(format!("{}", SpawnMode::SingleSession), "single-session");
        assert_eq!(format!("{}", SpawnMode::SameDir), "same-dir");
        assert_eq!(format!("{}", SpawnMode::Worktree), "worktree");
    }

    fn test_session_status_display() {
        assert_eq!(format!("{}", SessionStatus::Active), "active");
        assert_eq!(format!("{}", SessionStatus::Completed), "completed");
        assert_eq!(format!("{}", SessionStatus::Failed), "failed");
        assert_eq!(format!("{}", SessionStatus::Interrupted), "interrupted");
    }
}