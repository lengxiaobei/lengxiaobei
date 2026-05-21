package main

type Session struct {
	SessionID       string                 // Unique identifier for the session
	Process         interface{}            // Process associated with the session
	CurrentActivity map[string]interface{} // Current activity data (default: empty map)
	Activities      []interface{}          // List of activities (default: empty slice)
	LastStderr      []string               // Last stderr output (default: empty slice)
	AccessToken     string                 // Access token for authentication
}

func NewSession(sessionID string, process interface{}, currentActivity map[string]interface{}, activities []interface{}, lastStderr []string, accessToken string) *Session {
	session := &Session{
		SessionID:   sessionID,
		Process:     process,
		AccessToken: accessToken,
	}

	if currentActivity == nil {
		session.CurrentActivity = make(map[string]interface{})
	} else {
		session.CurrentActivity = currentActivity
	}

	if activities == nil {
		session.Activities = make([]interface{}, 0)
	} else {
		session.Activities = activities
	}

	if lastStderr == nil {
		session.LastStderr = make([]string, 0)
	} else {
		session.LastStderr = lastStderr
	}

	return session
}

func main() {
	// Main function
}