package main

import (
	"os/exec"
)

type Session struct {
	process *exec.Cmd
}

func (s *Session) Done() bool {
	return s.process.ProcessState != nil
}

func main() {
	// Main function
}