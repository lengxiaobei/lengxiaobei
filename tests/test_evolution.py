"""Tests for the evolution system — governance-embedded version."""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestModels:
    def test_evolution_phase_enum(self):
        from src.evolution.models import EvolutionPhase
        assert EvolutionPhase.DISCOVER.value == "discover"
        assert EvolutionPhase.VERIFY.value == "verify"

    def test_risk_level_enum(self):
        from src.evolution.models import RiskLevel
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_improvement_record_schema(self):
        from src.evolution.models import ImprovementRecord
        rec = ImprovementRecord(file="src/core.py", issue="test issue", priority="high", source="kairos")
        assert rec.file == "src/core.py"
        assert rec.issue == "test issue"
        assert rec.source == "kairos"
        assert rec.signature == "src/core.py:test issue"

    def test_improvement_record_from_kairos_file_path(self):
        from src.evolution.models import ImprovementRecord
        data = {"file_path": "src/test.py", "description": "fix bug"}
        rec = ImprovementRecord.from_kairos(data)
        assert rec is not None
        assert rec.file == "src/test.py"
        assert rec.issue == "fix bug"

    def test_improvement_record_from_kairos_file(self):
        from src.evolution.models import ImprovementRecord
        data = {"file": "src/test.py", "issue": "clean up"}
        rec = ImprovementRecord.from_kairos(data)
        assert rec is not None
        assert rec.file == "src/test.py"

    def test_improvement_record_from_kairos_missing_fields(self):
        from src.evolution.models import ImprovementRecord
        assert ImprovementRecord.from_kairos({}) is None
        assert ImprovementRecord.from_kairos({"file": "x.py"}) is None

    def test_improvement_record_to_dict(self):
        from src.evolution.models import ImprovementRecord
        rec = ImprovementRecord(file="a.py", issue="test", priority="low")
        d = rec.to_dict()
        assert d["file"] == "a.py"
        assert d["signature"] == "a.py:test"

    def test_improvement_record_abspath(self):
        from src.evolution.models import ImprovementRecord
        rec = ImprovementRecord(file="src/core.py", issue="test")
        path = rec.abspath("/project")
        assert path == "/project/src/core.py"

    def test_goal_creation(self):
        from src.evolution.models import Goal
        goal = Goal(description="test goal", constraints=["keep stable"])
        assert goal.description == "test goal"
        assert "keep stable" in goal.constraints


class TestLLMClient:
    def test_extract_json_simple(self):
        from src.evolution.llm_client import extract_json
        assert extract_json('{"key": "value"}') == {"key": "value"}

    def test_extract_json_nested(self):
        from src.evolution.llm_client import extract_json
        assert extract_json('{"outer": {"inner": [1, 2, 3]}}') == {"outer": {"inner": [1, 2, 3]}}

    def test_extract_json_with_markdown(self):
        from src.evolution.llm_client import extract_json
        assert extract_json('```json\n{"key": "value"}\n```') == {"key": "value"}

    def test_extract_json_with_noise(self):
        from src.evolution.llm_client import extract_json
        assert extract_json('here is some text {"result": true} and more text') == {"result": True}

    def test_extract_json_invalid(self):
        from src.evolution.llm_client import extract_json
        import json
        with pytest.raises(json.JSONDecodeError):
            extract_json("not json at all")


class TestCurator:
    def test_improvement_class(self):
        from src.evolution.curator import Improvement
        imp = Improvement(type="performance", file="src/core.py", issue="slow", priority="high")
        assert imp.file == "src/core.py"
        assert imp.priority == "high"

    def test_improvement_from_dict(self):
        from src.evolution.curator import Improvement
        data = {"type": "performance", "file": "src/core.py", "issue": "slow", "priority": "high", "confidence": 0.95}
        imp = Improvement.from_dict(data)
        assert imp.file == "src/core.py"
        assert imp.confidence == 0.95

    def test_curator_dedup(self):
        from src.evolution.curator import Curator
        c = Curator("/tmp")
        sig = "src/x.py:broken func"
        assert not c.is_duplicate(sig)
        c.mark_seen(sig)
        assert c.is_duplicate(sig)

    def test_curator_should_methods(self):
        from src.evolution.curator import Curator
        import time
        c = Curator("/tmp")
        assert c.should_quick_check()
        assert c.should_full_review()
        c._last_full_review = time.time()
        assert not c.should_full_review()

    def test_quick_check_finds_both_syntax_errors_and_missing_newlines(self, tmp_path):
        from src.evolution.curator import Curator

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "bad.py").write_text("def foo(x\n", encoding="utf-8")
        (src_dir / "no_newline.py").write_text("x = 1", encoding="utf-8")
        (src_dir / "ok.py").write_text("y = 1\n", encoding="utf-8")

        c = Curator(str(tmp_path))
        issues = c.quick_check()

        syntax_issues = [i for i in issues if i.type == "bug"]
        newline_issues = [i for i in issues if "文件末尾缺少换行" in i.issue]

        assert len(syntax_issues) >= 1, "应检测到语法错误"
        assert len(newline_issues) >= 1, "应检测到缺少末尾换行"


class TestExecutor:
    def test_sanitize_code_removes_markdown(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        result = executor._sanitize('```python\nprint("hello")\n```')
        assert 'print("hello")' in result
        assert "```" not in result

    def test_sanitize_preserves_final_newline(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        assert executor._sanitize("x = 1\n").endswith("\n")

    def test_validate_code_safety_valid(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        assert executor._validate_code_safety("print('hello')")

    def test_validate_code_safety_empty(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        assert not executor._validate_code_safety("")

    def test_validate_code_safety_llm_failure(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        assert not executor._validate_code_safety("[调用失败]")

    def test_execute_with_permission_granted(self):
        from src.evolution.executor import SafeExecutor
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("original = True\n")
            f.flush()
            file_path = f.name
        try:
            executor = SafeExecutor(os.path.dirname(file_path))
            result = executor.execute(file_path, "new = True\n")
            assert result.status == "success"
            with open(file_path) as f:
                assert "new" in f.read()
            executor.rollback(result)
            with open(file_path) as f:
                assert "original" in f.read()
            executor.cleanup(result)
            assert not os.path.exists(result.backup_path)
        finally:
            if os.path.exists(file_path):
                os.unlink(file_path)

    def test_execute_nonexistent_file(self):
        from src.evolution.executor import SafeExecutor
        executor = SafeExecutor("/tmp")
        result = executor.execute("/nonexistent/file.py", "code")
        assert result.status == "failed"
        assert "文件不存在" in result.error


class TestVerifier:
    def test_test_result_success(self):
        from src.evolution.verifier import TestResult
        r = TestResult(passed=5, failed=0, errors=0)
        assert r.success

    def test_test_result_failure(self):
        from src.evolution.verifier import TestResult
        r = TestResult(passed=5, failed=1, errors=0)
        assert not r.success

    def test_should_rollback(self):
        from src.evolution.verifier import TestResult, PytestVerifier
        v = PytestVerifier("/tmp")
        assert v.should_rollback(TestResult(failed=1))
        assert not v.should_rollback(TestResult(passed=10))

    def test_parse_pytest_output(self):
        from src.evolution.verifier import PytestVerifier
        v = PytestVerifier("/tmp")
        output = "=== 10 passed, 2 failed, 1 error in 0.5s ==="
        p, f, e, s = v._parse_pytest_output(output)
        assert p == 10
        assert f == 2
        assert e == 1

    def test_parse_pytest_output_passed_only(self):
        from src.evolution.verifier import PytestVerifier
        v = PytestVerifier("/tmp")
        output = "============================ 26 passed in 0.07s ==============================="
        p, f, e, s = v._parse_pytest_output(output)
        assert p == 26
        assert f == 0


class TestProposal:
    def test_proposal_from_dict(self):
        from src.evolution.proposer import Proposal
        data = {"improvement_type": "performance", "file_path": "src/core.py",
                "original_issue": "slow", "steps": ["s1", "s2"]}
        p = Proposal.from_dict(data)
        assert p.original_issue == "slow"
        assert len(p.steps) == 2

    def test_proposal_defaults(self):
        from src.evolution.proposer import Proposal
        p = Proposal.from_dict({})
        assert p.risk_level == "low"

    def test_final_newline_fix_is_deterministic(self, tmp_path):
        from src.evolution.proposer import Proposer
        proposer = Proposer(str(tmp_path))
        proposal = proposer.propose(
            {
                "type": "code_quality",
                "file": "src/example.py",
                "issue": "文件末尾缺少换行，补齐 POSIX 文本文件结尾",
            },
            "x = 1",
        )
        assert proposal.risk_level == "low"
        assert proposer.generate_new_code("x = 1", proposal) == "x = 1\n"


class TestEngineInstantiation:
    def test_create_engine(self):
        from src.evolution.engine import create_autonomous_evolution_engine
        engine = create_autonomous_evolution_engine()
        assert engine is not None
        assert engine.curator is not None
        assert engine.proposer is not None
        assert engine.executor is not None
        assert engine.verifier is not None

    def test_evolve_file_not_found(self):
        from src.evolution.engine import create_autonomous_evolution_engine
        engine = create_autonomous_evolution_engine()
        result = engine.evolve("/nonexistent/file.py", "test")
        assert result["status"] == "failed"
        assert "error" in result

    def test_evolve_dry_run_accepts_param(self):
        from src.evolution.engine import create_autonomous_evolution_engine
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        try:
            engine = create_autonomous_evolution_engine()
            result = engine.evolve(path, "add comment", dry_run=True)
            assert isinstance(result, dict)
            assert "status" in result
        finally:
            os.unlink(path)

    def test_cooldown(self):
        from src.evolution.engine import create_autonomous_evolution_engine
        import time
        engine = create_autonomous_evolution_engine()
        engine.last_evolution_time = time.time()
        engine.evolution_cooldown = 300
        result = engine.evolve_autonomously()
        assert result["status"] == "cooldown"

    def test_autonomous_final_newline_e2e(self, tmp_path):
        from src.evolution.engine import create_autonomous_evolution_engine
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        target = src_dir / "sample.py"
        target.write_text("x = 1", encoding="utf-8")

        engine = create_autonomous_evolution_engine(project_root=str(tmp_path))
        engine.evolution_cooldown = 0
        result = engine.evolve_autonomously()

        assert result["status"] == "success"
        assert target.read_text(encoding="utf-8") == "x = 1\n"
