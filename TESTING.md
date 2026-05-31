# KineticSketch AI - Testing Guide

Comprehensive testing setup for KineticSketch AI with unit tests, integration tests, and code quality checks.

## Quick Start

### Install Testing Dependencies

```bash
# Install test requirements
pip install -r requirements-test.txt
```

### Run All Tests

```bash
# Run all tests with coverage report
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest test_cheminformatics.py

# Run specific test class
pytest test_cheminformatics.py::TestSMILESParsing

# Run specific test
pytest test_cheminformatics.py::TestSMILESParsing::test_valid_smiles_ethane
```

---

## Test Structure

### Unit Tests

#### `test_cheminformatics.py`
Tests for molecular structure processing (RDKit, 3D optimization, file export):
- SMILES parsing and validation
- 2D coordinate generation
- 3D conformer optimization (MMFF94)
- File format conversion (SDF, XYZ, MOL2)
- Edge cases (empty SMILES, large molecules, charged species)

**Run:** `pytest test_cheminformatics.py -v`

#### `test_models.py`
Tests for PyTorch ML model (MDRepoPredictor):
- Model initialization and device management
- Forward pass inference
- Output shape and value validation
- Batch processing
- Input validation and error handling
- Memory efficiency

**Run:** `pytest test_models.py -v`

### Integration Tests

#### `test_integration.py`
End-to-end tests for complete pipeline:
- SMILES → 3D → Predictions → File Export
- Error handling and graceful degradation
- Molecular size limits and robustness
- Batch processing consistency
- Performance benchmarks

**Run:** `pytest test_integration.py -v`

---

## Running Tests by Category

### All Unit Tests
```bash
pytest -m unit -v
```

### All Integration Tests
```bash
pytest -m integration -v
```

### Performance Tests
```bash
pytest -m performance -v
```

### Skip Slow Tests
```bash
pytest -m "not slow" -v
```

### Only Tests Requiring PyMOL
```bash
pytest -m requires_pymol -v
```

---

## Test Reports

### Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=. --cov-report=html

# View report (opens in browser)
open htmlcov/index.html
```

### Generate Report Summary

```bash
# Show coverage in terminal
pytest --cov=. --cov-report=term-missing

# Example output:
# Name                     Stmts   Miss  Cover   Missing
# -------------------------------------------------------
# cheminformatics.py        150    12    92%    45-47, 123-130
# models.py                 85     3     96%    112-114
# visualizer.py            120    8     93%    67-74
# -------------------------------------------------------
# TOTAL                    355    23    93%
```

---

## Running Specific Test Suites

### SMILES Validation Tests
```bash
pytest test_cheminformatics.py::TestSMILESParsing -v
```

### 3D Structure Generation Tests
```bash
pytest test_cheminformatics.py::TestMolecularStructure -v
```

### File Format Export Tests
```bash
pytest test_cheminformatics.py::TestFileFormats -v
```

### Model Inference Tests
```bash
pytest test_models.py::TestModelInference -v
```

### Full Pipeline Tests
```bash
pytest test_integration.py::TestFullPipeline -v
```

### Error Handling Tests
```bash
pytest test_integration.py::TestPipelineErrorHandling -v
```

---

## Code Quality Checks

### Type Checking with MyPy

```bash
# Check type hints across codebase
mypy kinetic_sketch.py visualizer.py models.py cheminformatics.py

# Generate report
mypy --html mypy-report kinetic_sketch.py
```

### Linting with Flake8

```bash
# Check code style
flake8 *.py --max-line-length=100

# Example findings:
# kinetic_sketch.py:42:1: E302 expected 2 blank lines, found 1
# models.py:15:1: F401 'torch.nn' imported but unused
```

### Code Formatting with Black

```bash
# Check formatting
black --check *.py

# Auto-fix formatting
black *.py
```

### Import Sorting with isort

```bash
# Check import order
isort --check *.py

# Fix import order
isort *.py
```

### Full Quality Check

```bash
# Run all checks
./run_checks.sh  # (if script exists)

# Or manually:
black --check *.py
flake8 *.py
mypy *.py
pytest --cov=.
```

---

## Continuous Integration

### GitHub Actions Example

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run tests
        run: pytest --cov=. --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## Debugging Tests

### Run Single Test with Debugging

```bash
# Run with print statements visible
pytest test_cheminformatics.py::TestSMILESParsing::test_valid_smiles_ethane -s

# Run with pdb debugger
pytest test_models.py -k "test_output_shape" --pdb
```

### Show Local Variables on Error

```bash
pytest --tb=long test_integration.py
```

### Increase Verbosity

```bash
pytest -vv test_cheminformatics.py
```

---

## Performance Benchmarking

### Run Performance Tests

```bash
pytest test_integration.py::TestPerformance -v

# Expected results:
# test_processing_time_reasonable: 1.2s (Ibuprofen processing)
# test_batch_prediction_time: 0.08s (10 structures)
```

### Benchmark Specific Function

```bash
pytest test_integration.py::TestPerformance::test_processing_time_reasonable --benchmark-only
```

### Memory Profiling

```bash
python -m memory_profiler test_integration.py
```

---

## Test Data

### Molecule SMILES Used in Tests

| Molecule | SMILES | Atoms | Use Case |
|----------|--------|-------|----------|
| Ethane | CC | 8 | Simple structure |
| Benzene | c1ccccc1 | 12 | Aromatic ring |
| Aspirin | O=C(O)c1ccccc1OC(=O)C | 21 | Drug compound |
| Ibuprofen | CC(C)Cc1ccc(cc1)C(C)C(=O)O | 17 | Complex drug |
| Paracetamol | CC(=O)Nc1ccc(cc1)O | 15 | Common analgesic |
| Caffeine | CN1C=NC2=C1C(=O)N(C(=O)N2C)C | 24 | Stimulant |
| Cholesterol | CC(C)CCCC(C)C1CCC2C1(CCC3=C2CC=C4=CC(CCC4=C3)O)C | 73 | Large lipid |

---

## Expected Test Coverage

### Coverage Targets

- **Core modules**: >90% coverage
- **cheminformatics.py**: 92% (some edge cases in 3D optimization)
- **models.py**: 96% (model internals)
- **visualizer.py**: 85% (external service dependencies)
- **Overall**: >85%

### Coverage Report Sample

```
Name                        Stmts   Miss  Cover
-----------------------------------------------
cheminformatics.py          150    12    92%
models.py                    85     3    96%
visualizer.py              120    18    85%
pdb_repurposing.py          95     8    92%
checkpoint.py               60     4    93%
kinetic_sketch.py          420    52    88%
-----------------------------------------------
TOTAL                     930    97    90%
```

---

## Troubleshooting Tests

### Test Fails: "Module not found"

```bash
# Ensure you're in the project root directory
cd /path/to/KineticSketch

# Reinstall dependencies
pip install -r requirements.txt
```

### Test Fails: "CUDA out of memory"

```bash
# Force CPU-only mode
export CUDA_VISIBLE_DEVICES=""
pytest test_models.py -v
```

### Test Timeout

```bash
# Increase timeout from 300s to 600s
pytest --timeout=600 test_integration.py
```

### Intermittent Failures

```bash
# Run test multiple times to identify flakiness
pytest test_cheminformatics.py --count=10
```

---

## Pre-Commit Checks

### Install Pre-Commit Hook

```bash
# Install pre-commit framework
pip install pre-commit

# Install hooks
pre-commit install
```

### Pre-Commit Config (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
  
  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
  
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
```

---

## Contributing Tests

### Adding New Tests

1. Create test file: `test_new_feature.py`
2. Use existing test patterns
3. Add docstrings explaining test purpose
4. Use meaningful assertion messages
5. Mark with appropriate markers (`@pytest.mark.unit`, etc.)
6. Ensure >90% coverage on modified code

### Test Template

```python
class TestNewFeature:
    """Tests for new feature."""

    def test_happy_path(self):
        """Test successful operation."""
        result = new_function(valid_input)
        assert result == expected_output

    def test_error_handling(self):
        """Test graceful error handling."""
        with pytest.raises(ValueError):
            new_function(invalid_input)

    @pytest.mark.slow
    def test_performance(self):
        """Test performance requirements."""
        # Test code here
        pass
```

---

## CI/CD Integration

### Local Pre-Push Check

```bash
#!/bin/bash
# Run before pushing to GitHub
set -e

echo "Running tests..."
pytest --cov=.

echo "Checking code quality..."
black --check *.py
flake8 *.py

echo "✓ All checks passed!"
```

---

## Support

For test-related issues:
1. Check pytest output for detailed error messages
2. Review test code comments for expected behavior
3. Consult test documentation above
4. Enable verbose mode: `pytest -vv`

---

**Last Updated:** 2024-01-15  
**Version:** 1.0.0
