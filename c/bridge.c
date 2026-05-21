#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: bridge <command> [args]\n");
        printf("Commands:\n");
        printf("  spawn <session_id> <sdk_url> <access_token> - Spawn a new session\n");
        return 1;
    }

    char *command = argv[1];
    
    if (strcmp(command, "spawn") == 0) {
        if (argc < 5) {
            printf("Usage: bridge spawn <session_id> <sdk_url> <access_token>\n");
            return 1;
        }

        char *session_id = argv[2];
        char *sdk_url = argv[3];
        char *access_token = argv[4];

        // 模拟会话生成
        printf("Session spawned successfully: %s\n", session_id);
        printf("SDK URL: %s\n", sdk_url);
        printf("Access Token: %s\n", access_token);
        printf("Starting session process...\n");

        // 启动一个实际的进程
        pid_t pid = fork();
        if (pid == 0) {
            // 子进程
            execlp("python3", "python3", "-c", "import time; print('Session process started'); time.sleep(5)", NULL);
            perror("execlp");
            exit(1);
        } else if (pid > 0) {
            // 父进程
            // 等待进程启动
            sleep(1);
            printf("Session process started successfully\n");
            // 等待子进程结束
            wait(NULL);
        } else {
            // fork 失败
            perror("fork");
            return 1;
        }
    } else {
        printf("Unknown command: %s\n", command);
        printf("Usage: bridge <command> [args]\n");
        printf("Commands:\n");
        printf("  spawn <session_id> <sdk_url> <access_token> - Spawn a new session\n");
        return 1;
    }

    return 0;
}
