"""
安全审计模块
============
提供安全扫描、密钥检测、环境变量验证等功能
"""
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Set


# =============================================================================
# Secret Patterns
# =============================================================================

SECRET_PATTERNS = [
    # Generic API keys
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', 'API Key'),
    # AWS keys
    (r'AKIA[0-9A-Z]{16}', 'AWS Access Key'),
    # GitHub tokens
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Personal Access Token'),
    (r'github_pat_[a-zA-Z0-9_]{22,}', 'GitHub Fine-grained Token'),
    # OpenAI keys
    (r'sk-[a-zA-Z0-9]{48}', 'OpenAI API Key'),
    # Anthropic keys
    (r'sk-ant-[a-zA-Z0-9]{51}', 'Anthropic API Key'),
    # JWT tokens
    (r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', 'JWT Token'),
    # Private keys
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 'Private Key'),
    # Database passwords
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{8,})["\']?', 'Password'),
    # MiniMax keys
    (r'(?i)minimax[_-]?(api)?[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9]{32,})["\']?', 'MiniMax API Key'),
]

# Files to exclude from scanning
EXCLUDED_PATTERNS = [
    r'__pycache__',
    r'\.git/',
    r'\.venv/',
    r'node_modules/',
    r'\.pyc',
    r'coverage\.xml',
    r'\.log',
    r'passwords\.txt',
]

# =============================================================================
# Security Scanner
# =============================================================================

class SecurityScanResult:
    def __init__(self):
        self.secrets_found: List[Dict] = []
        self.files_scanned = 0
        self.issues: List[Dict] = []

    def add_secret(self, file_path: str, line_number: int, line_content: str,
                   secret_type: str, matched_value: str = None):
        self.secrets_found.append({
            "file": file_path,
            "line": line_number,
            "content": line_content.strip()[:100],
            "type": secret_type,
            "matched": matched_value[:20] + "..." if matched_value and len(matched_value) > 20 else matched_value
        })

    def add_issue(self, severity: str, message: str, file_path: str = None):
        self.issues.append({
            "severity": severity,  # low, medium, high, critical
            "message": message,
            "file": file_path
        })

    def to_json(self) -> str:
        return json.dumps({
            "secrets_found": self.secrets_found,
            "files_scanned": self.files_scanned,
            "issues": self.issues,
            "has_secrets": len(self.secrets_found) > 0,
            "has_critical": any(i["severity"] == "critical" for i in self.issues)
        }, indent=2)

    def has_secrets(self) -> bool:
        return len(self.secrets_found) > 0

    def summary(self) -> str:
        lines = [
            f"Files scanned: {self.files_scanned}",
            f"Secrets found: {len(self.secrets_found)}",
            f"Issues: {len(self.issues)}"
        ]
        if self.secrets_found:
            lines.append("\nSecrets detected:")
            for s in self.secrets_found:
                lines.append(f"  [{s['type']}] {s['file']}:{s['line']}")
        return "\n".join(lines)


def scan_file_for_secrets(file_path: Path) -> List[Dict]:
    """扫描单个文件中的密钥"""
    secrets = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments in various languages
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('//'):
                    continue

                for pattern, secret_type in SECRET_PATTERNS:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        # Get the matched value
                        matched = match.group(0)
                        # Mask it for reporting
                        if len(matched) > 20:
                            masked = matched[:8] + "..." + matched[-4:]
                        else:
                            masked = matched[:4] + "****"

                        secrets.append({
                            "line": line_num,
                            "content": line.strip()[:100],
                            "type": secret_type,
                            "matched": masked
                        })
    except Exception:
        pass

    return secrets


def scan_directory(root_dir: Path, exclude_patterns: List[str] = None) -> SecurityScanResult:
    """扫描目录中的安全问题"""
    result = SecurityScanResult()
    exclude_patterns = exclude_patterns or EXCLUDED_PATTERNS

    # File extensions to scan
    scan_extensions = {
        '.py', '.js', '.ts', '.json', '.yaml', '.yml',
        '.env', '.ini', '.cfg', '.conf', '.sh', '.bash',
        '.txt', '.md', '.toml'
    }

    for file_path in root_dir.rglob('*'):
        if not file_path.is_file():
            continue

        # Check exclusions
        path_str = str(file_path)
        if any(re.search(p, path_str) for p in exclude_patterns):
            continue

        # Only scan specific file types
        if file_path.suffix.lower() not in scan_extensions:
            continue

        result.files_scanned += 1

        # Scan for secrets
        secrets = scan_file_for_secrets(file_path)
        for secret in secrets:
            result.add_secret(
                str(file_path.relative_to(root_dir)),
                secret["line"],
                secret["content"],
                secret["type"],
                secret["matched"]
            )

        # Check for other issues
        check_file_issues(file_path, result)

    return result


def check_file_issues(file_path: Path, result: SecurityScanResult):
    """检查文件特定问题"""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')

        # Check for hardcoded passwords
        if re.search(r'password\s*=\s*["\'][^"\']{8,}["\']', content):
            result.add_issue(
                "high",
                "Hardcoded password detected",
                str(file_path)
            )

        # Check for eval() usage
        if re.search(r'\beval\s*\(', content):
            result.add_issue(
                "high",
                "Dangerous eval() usage detected",
                str(file_path)
            )

        # Check for subprocess with shell=True
        if re.search(r'subprocess\..*shell\s*=\s*True', content):
            result.add_issue(
                "medium",
                "subprocess with shell=True can be dangerous",
                str(file_path)
            )

        # Check for SQL injection risk
        if re.search(r'execute\s*\(\s*f["\']', content):
            result.add_issue(
                "medium",
                "Potential SQL injection risk (f-string in execute)",
                str(file_path)
            )

        # Check for insecure hash algorithms
        if re.search(r'md5\s*\(|hashlib\.md5\(', content):
            result.add_issue(
                "low",
                "MD5 is cryptographically broken, consider SHA-256",
                str(file_path)
            )

    except Exception:
        pass


# =============================================================================
# Environment Variable Validator
# =============================================================================

REQUIRED_SECRETS = [
    "LLM_API_KEY",
    # Add other required secrets as needed
]

OPTIONAL_SECRETS = [
    "QDRANT_URL",
    "HF_TOKEN",
    "DOCKER_USERNAME",
]


def validate_environment() -> Dict[str, any]:
    """验证环境变量配置"""
    result = {
        "valid": True,
        "missing_required": [],
        "missing_optional": [],
        "warnings": []
    }

    for secret in REQUIRED_SECRETS:
        if secret not in os.environ or not os.environ[secret]:
            result["missing_required"].append(secret)
            result["valid"] = False

    for secret in OPTIONAL_SECRETS:
        if secret not in os.environ or not os.environ[secret]:
            result["missing_optional"].append(secret)

    # Check for common issues
    if "PYTHONPATH" in os.environ:
        result["warnings"].append("PYTHONPATH is set, may cause import issues")

    if os.environ.get("DEBUG", "").lower() == "true":
        result["warnings"].append("DEBUG mode is enabled")

    return result


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="LengXiaobei Security Scanner")
    parser.add_argument("directory", nargs="?", default=".", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--fail-on-secrets", action="store_true", help="Exit with error if secrets found")

    args = parser.parse_args()

    root = Path(args.directory).resolve()
    result = scan_directory(root)

    if args.json:
        print(result.to_json())
    else:
        print(result.summary())

    if args.fail_on_secrets and result.has_secrets():
        exit(1)


if __name__ == "__main__":
    main()
