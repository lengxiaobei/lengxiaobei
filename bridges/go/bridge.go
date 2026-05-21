package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
)

type SpawnMode string

const (
	SingleSession SpawnMode = "single-session"
	SameDir       SpawnMode = "same-dir"
	Worktree      SpawnMode = "worktree"
)

type SessionStatus string

const (
	Active      SessionStatus = "active"
	Completed   SessionStatus = "completed"
	Failed      SessionStatus = "failed"
	Interrupted SessionStatus = "interrupted"
)

type BridgeConfig struct {
	APIBaseURL         string
	SessionIngressURL  string
	Dir                string
	MaxSessions        int
	SpawnMode          SpawnMode
	SessionTimeoutMs   *int
	DebugFile          *string
	Verbose            bool
}

func NewBridgeConfig(apiBaseURL, sessionIngressURL, dir string, maxSessions int, spawnMode SpawnMode, sessionTimeoutMs *int, debugFile *string, verbose bool) *BridgeConfig {
	return &BridgeConfig{
		APIBaseURL:        apiBaseURL,
		SessionIngressURL: sessionIngressURL,
		Dir:               dir,
		MaxSessions:       maxSessions,
		SpawnMode:         spawnMode,
		SessionTimeoutMs:  sessionTimeoutMs,
		DebugFile:         debugFile,
		Verbose:           verbose,
	}
}

func CreateBridgeConfig(apiBaseURL, sessionIngressURL, dir string, maxSessions int, spawnMode SpawnMode) *BridgeConfig {
	return NewBridgeConfig(apiBaseURL, sessionIngressURL, dir, maxSessions, spawnMode, nil, nil, false)
}

type SessionHandle struct {
	SessionID       string
	Process         *exec.Cmd
	CurrentActivity map[string]interface{}
	Activities      []map[string]interface{}
	LastStderr      []string
	AccessToken     *string
}

func NewSessionHandle(sessionID string, process *exec.Cmd, currentActivity map[string]interface{}, activities []map[string]interface{}, lastStderr []string, accessToken *string) *SessionHandle {
	if currentActivity == nil {
		currentActivity = make(map[string]interface{})
	}
	if activities == nil {
		activities = []map[string]interface{}{}
	}
	if lastStderr == nil {
		lastStderr = []string{}
	}
	return &SessionHandle{
		SessionID:       sessionID,
		Process:         process,
		CurrentActivity: currentActivity,
		Activities:      activities,
		LastStderr:      lastStderr,
		AccessToken:     accessToken,
	}
}

func (sh *SessionHandle) UpdateAccessToken(token string) {
	sh.AccessToken = &token
}

func (sh *SessionHandle) Done() bool {
	if sh.Process == nil || sh.Process.ProcessState != nil {
		return true
	}
	return false
}

type SessionSpawnOpts struct {
	SessionID            string
	SDKURL               string
	AccessToken          string
	UseCCRv2             bool
	WorkerEpoch          *int
	OnFirstUserMessage   func(string)
}

func NewSessionSpawnOpts(sessionID, sdkURL, accessToken string, useCCRv2 bool, workerEpoch *int, onFirstUserMessage func(string)) *SessionSpawnOpts {
	return &SessionSpawnOpts{
		SessionID:          sessionID,
		SDKURL:             sdkURL,
		AccessToken:        accessToken,
		UseCCRv2:           useCCRv2,
		WorkerEpoch:        workerEpoch,
		OnFirstUserMessage: onFirstUserMessage,
	}
}

type SessionSpawner struct{}

func (ss *SessionSpawner) Spawn(opts *SessionSpawnOpts, dir string) (*SessionHandle, error) {
	useGoImplementation := true // Default to using Go implementation
	if useGoImplementation {
		return ss.spawnWithGo(opts)
	}
	return ss.spawnWithGo(opts) // Fallback to Go implementation
}

func (ss *SessionSpawner) spawnWithGo(opts *SessionSpawnOpts) (*SessionHandle, error) {
	goBridgePath := filepath.Join(filepath.Dir(os.Args[0]), "bridge")
	cmd := exec.Command(goBridgePath, "spawn", opts.SessionID, opts.SDKURL, opts.AccessToken)
	err := cmd.Start()
	if err != nil {
		fmt.Printf("[Bridge] Go implementation call failed: %v\n", err)
		
		rustResult, err := ss.trySpawnWithRust(opts)
		if err == nil && rustResult != nil {
			return rustResult, nil
		}
		
		tsResult, err := ss.trySpawnWithTypescript(opts)
		if err == nil && tsResult != nil {
			return tsResult, nil
		}
		
		cResult, err := ss.trySpawnWithC(opts)
		if err == nil && cResult != nil {
			return cResult, nil
		}
		
		return ss.spawnWithGo(opts)
	}
	
	return ss.createSessionHandleFromExternalResult(opts, "Go"), nil
}

func (ss *SessionSpawner) trySpawnWithRust(opts *SessionSpawnOpts) (*SessionHandle, error) {
	rustBridgePath := filepath.Join(filepath.Dir(os.Args[0]), "bridge_rust")
	if _, err := os.Stat(rustBridgePath); err == nil {
		fmt.Println("[Bridge] Using Rust implementation")
		cmd := exec.Command(rustBridgePath, "spawn", opts.SessionID, opts.SDKURL, opts.AccessToken)
		err := cmd.Start()
		if err != nil {
			fmt.Printf("[Bridge] Rust implementation execution failed: %v\n", err)
			return nil, err
		}
		return ss.createSessionHandleFromExternalResult(opts, "Rust"), nil
	}
	return nil, fmt.Errorf("rust bridge not found")
}

func (ss *SessionSpawner) trySpawnWithTypescript(opts *SessionSpawnOpts) (*SessionHandle, error) {
	tsBridgePath := filepath.Join(filepath.Dir(os.Args[0]), "bridge_ts")
	if _, err := os.Stat(tsBridgePath); err == nil {
		fmt.Println("[Bridge] Using TypeScript implementation")
		cmd := exec.Command("node", tsBridgePath, "spawn", opts.SessionID, opts.SDKURL, opts.AccessToken)
		err := cmd.Start()
		if err != nil {
			fmt.Printf("[Bridge] TypeScript implementation execution failed: %v\n", err)
			return nil, err
		}
		return ss.createSessionHandleFromExternalResult(opts, "TypeScript"), nil
	}
	return nil, fmt.Errorf("typescript bridge not found")
}

func (ss *SessionSpawner) trySpawnWithC(opts *SessionSpawnOpts) (*SessionHandle, error) {
	cBridgePath := filepath.Join(filepath.Dir(os.Args[0]), "bridge_c")
	if _, err := os.Stat(cBridgePath); err == nil {
		fmt.Println("[Bridge] Using C implementation")
		cmd := exec.Command(cBridgePath, "spawn", opts.SessionID, opts.SDKURL, opts.AccessToken)
		err := cmd.Start()
		if err != nil {
			fmt.Printf("[Bridge] C implementation execution failed: %v\n", err)
			return nil, err
		}
		return ss.createSessionHandleFromExternalResult(opts, "C"), nil
	}
	return nil, fmt.Errorf("c bridge not found")
}

func (ss *SessionSpawner) createSessionHandleFromExternalResult(opts *SessionSpawnOpts, implementation string) *SessionHandle {
	cmd := exec.Command("echo", fmt.Sprintf("session spawned by %s", implementation))
	cmd.Start()
	
	return NewSessionHandle(
		opts.SessionID,
		cmd,
		nil,
		nil,
		nil,
		&opts.AccessToken,
	)
}

func CreateSessionSpawner() *SessionSpawner {
	return &SessionSpawner{}
}

type BridgeAPIClient struct {
	BaseURL string
}

func NewBridgeAPIClient(baseURL string) *BridgeAPIClient {
	return &BridgeAPIClient{BaseURL: baseURL}
}

func (b *BridgeAPIClient) PollForWork(ctx context.Context, environmentID, environmentSecret string, signal chan os.Signal, reclaimOlderThanMs int) (map[string]interface{}, error) {
	return b.performPolling(ctx, environmentID, environmentSecret, signal, reclaimOlderThanMs)
}

func (b *BridgeAPIClient) performPolling(ctx context.Context, environmentID, environmentSecret string, signal chan os.Signal, reclaimOlderThanMs int) (map[string]interface{}, error) {
	return nil, nil
}

func (b *BridgeAPIClient) AcknowledgeWork(ctx context.Context, environmentID, workID, token string) error {
	return b.sendAcknowledgment(ctx, environmentID, workID, token)
}

func (b *BridgeAPIClient) sendAcknowledgment(ctx context.Context, environmentID, workID, token string) error {
	return nil
}

func (b *BridgeAPIClient) HeartbeatWork(ctx context.Context, environmentID, workID, token string) error {
	return b.sendHeartbeat(ctx, environmentID, workID, token)
}

func (b *BridgeAPIClient) sendHeartbeat(ctx context.Context, environmentID, workID, token string) error {
	return nil
}

func (b *BridgeAPIClient) StopWork(ctx context.Context, environmentID, workID string) error {
	return b.stopSpecificWork(ctx, environmentID, workID)
}

func (b *BridgeAPIClient) stopSpecificWork(ctx context.Context, environmentID, workID string) error {
	return nil
}

func (b *BridgeAPIClient) ReconnectSession(ctx context.Context, environmentID, sessionID string) error {
	return b.performReconnection(ctx, environmentID, sessionID)
}

func (b *BridgeAPIClient) performReconnection(ctx context.Context, environmentID, sessionID string) error {
	return nil
}

func (b *BridgeAPIClient) ArchiveSession(ctx context.Context, sessionID string) error {
	return b.archiveSpecificSession(ctx, sessionID)
}

func (b *BridgeAPIClient) archiveSpecificSession(ctx context.Context, sessionID string) error {
	return nil
}

func CreateBridgeAPIClient(baseURL string) *BridgeAPIClient {
	return NewBridgeAPIClient(baseURL)
}

type BridgeLogger struct {
	sessions       map[string]interface{}
	activeSessions int
	maxSessions    int
	spawnMode      SpawnMode
}

func NewBridgeLogger() *BridgeLogger {
	return &BridgeLogger{
		sessions:       make(map[string]interface{}),
		activeSessions: 0,
		maxSessions:    1,
		spawnMode:      SingleSession,
	}
}

func (bl *BridgeLogger) PrintBanner(config *BridgeConfig, environmentID string) {
	bannerMsg := fmt.Sprintf("Bridge started with environment: %s", environmentID)
	fmt.Println(bannerMsg)
}

func (bl *BridgeLogger) LogSessionStart(sessionID, description string) {
	startMsg := fmt.Sprintf("Session started: %s - %s", sessionID, description)
	fmt.Println(startMsg)
}

func (bl *BridgeLogger) LogSessionComplete(sessionID string, durationMs int) {
	completeMsg := fmt.Sprintf("Session completed: %s - %dms", sessionID, durationMs)
	fmt.Println(completeMsg)
}

func (bl *BridgeLogger) LogSessionFailed(sessionID, message string) {
	failMsg := fmt.Sprintf("Session failed: %s - %s", sessionID, message)
	fmt.Println(failMsg)
}

func (bl *BridgeLogger) LogError(message string) {
	errorMsg := fmt.Sprintf("Error: %s", message)
	fmt.Println(errorMsg)
}

func (bl *BridgeLogger) LogVerbose(message string) {
	verboseMsg := fmt.Sprintf("Verbose: %s", message)
	fmt.Println(verboseMsg)
}

func (bl *BridgeLogger) LogReconnected(disconnectedMs int) {
	reconnMsg := fmt.Sprintf("Reconnected after %dms", disconnectedMs)
	fmt.Println(reconnMsg)
}

func (bl *BridgeLogger) SetAttached(sessionID string) {
}

func (bl *BridgeLogger) UpdateSessionCount(count, maxCount int, spawnMode SpawnMode) {
	bl.activeSessions = count
	bl.maxSessions = maxCount
	bl.spawnMode = spawnMode
}

func (bl *BridgeLogger) UpdateIdleStatus() {
}

func (bl *BridgeLogger) UpdateSessionStatus(sessionID, elapsed string, activity map[string]interface{}, trail []string) {
}

func (bl *BridgeLogger) AddSession(sessionID, url string) {
}

func (bl *BridgeLogger) RemoveSession(sessionID string) {
}

func (bl *BridgeLogger) SetSessionTitle(sessionID, title string) {
}

func (bl *BridgeLogger) UpdateSessionActivity(sessionID string, activity map[string]interface{}) {
}

func (bl *BridgeLogger) RefreshDisplay() {
}

func (bl *BridgeLogger) ClearStatus() {
}

func (bl *BridgeLogger) SetDebugLogPath(path string) {
}

func CreateBridgeLogger() *BridgeLogger {
	return NewBridgeLogger()
}

func RunBridgeLoop(
	ctx context.Context,
	config *BridgeConfig,
	environmentID, environmentSecret string,
	api *BridgeAPIClient,
	spawner *SessionSpawner,
	logger *BridgeLogger,
	signal chan os.Signal,
	initialSessionID *string,
) error {
	err := initializeBridge(config, environmentID, logger)
	if err != nil {
		return err
	}
	
	return startMainLoop(ctx, config, environmentID, environmentSecret, api, spawner, logger, signal, initialSessionID)
}

func initializeBridge(config *BridgeConfig, environmentID string, logger *BridgeLogger) error {
	logger.PrintBanner(config, environmentID)
	return nil
}

func startMainLoop(
	ctx context.Context,
	config *BridgeConfig,
	environmentID, environmentSecret string,
	api *BridgeAPIClient,
	spawner *SessionSpawner,
	logger *BridgeLogger,
	signal chan os.Signal,
	initialSessionID *string,
) error {
	fmt.Println("Bridge loop started")
	
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case sig := <-signal:
			fmt.Printf("Received signal: %s\n", sig)
			return nil
		default:
			time.Sleep(100 * time.Millisecond)
		}
	}
}

type BridgeClient = BridgeAPIClient

func main() {
	config := CreateBridgeConfig("http://example.com", "http://ingress.example.com", "/tmp", 1, SingleSession)
	
	sessionSpawner := CreateSessionSpawner()
	
	logger := CreateBridgeLogger()
	
	apiClient := CreateBridgeAPIClient("http://api.example.com")
	
	signalChan := make(chan os.Signal, 1)
	
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	
	initialSessionID := "test-session-id"
	
	err := RunBridgeLoop(ctx, config, "env-123", "secret-456", apiClient, sessionSpawner, logger, signalChan, &initialSessionID)
	if err != nil {
		fmt.Printf("Bridge loop error: %v\n", err)
	}
}