package main

import (
	"fmt"
)

type SessionSpawnOpts struct {
	SessionID   string `json:"session_id"`
	SdkURL      string `json:"sdk_url"`
	AccessToken string `json:"access_token"`
	UseCCRv2    bool   `json:"use_ccr_v2"`
	WorkerEpoch int    `json:"worker_epoch"`
}

type SessionHandle struct {
	SessionID   string
	Process     interface{} // Go中可能不需要直接管理进程，用interface{}表示
	AccessToken string
}

func SpawnSession(opts SessionSpawnOpts, dir string) (map[string]interface{}, error) {
	result := map[string]interface{}{
		"session_id":   opts.SessionID,
		"access_token": opts.AccessToken,
	}
	
	fmt.Printf("Spawning session in directory: %s\n", dir)
	fmt.Printf("Session options: %+v\n", opts)
	
	return result, nil
}

func spawn(opts SessionSpawnOpts, dir string) (*SessionHandle, error) {
	
	goOpts := map[string]interface{}{
		"session_id":   opts.SessionID,
		"sdk_url":      opts.SdkURL,
		"access_token": opts.AccessToken,
		"use_ccr_v2":   opts.UseCCRv2,
		"worker_epoch": opts.WorkerEpoch,
	}
	
	handleData, err := SpawnSession(opts, dir)
	if err != nil {
		return nil, err
	}
	
	return &SessionHandle{
		SessionID:   handleData["session_id"].(string),
		Process:     nil, // Go实现管理进程
		AccessToken: handleData["access_token"].(string),
	}, nil
}

func main() {
	opts := SessionSpawnOpts{
		SessionID:   "test-session",
		SdkURL:      "https://api.example.com",
		AccessToken: "test-token",
		UseCCRv2:    true,
		WorkerEpoch: 0,
	}
	
	handle, err := spawn(opts, "/tmp/session")
	if err != nil {
		fmt.Printf("Error spawning session: %v\n", err)
		return
	}
	
	fmt.Printf("Session spawned: %+v\n", handle)
}