$ErrorActionPreference = "Stop"

function Invoke-CIGate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host $Name

    & $Command

    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Invoke-CIGate "1/7 Poetry lock validation" {
    poetry check --lock
}

Invoke-CIGate "2/7 Ruff" {
    poetry run ruff check .
}

Invoke-CIGate "3/7 Mypy baseline" {
    poetry run mypy core services dependencies.py database.py models.py schemas.py
}

Invoke-CIGate "4/7 Alembic upgrade" {
    poetry run alembic upgrade head
}

Invoke-CIGate "5/7 Alembic drift check" {
    poetry run alembic check
}

Invoke-CIGate "6/7 Pytest" {
    poetry run pytest -q
}

Invoke-CIGate "7/7 Dependency audit" {
    poetry run pip-audit
}

Write-Host ""
Write-Host "All local CI gates passed."
