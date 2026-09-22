# TemplateResponse warnings + GitHub Actions CI

## 1. Put these files into the project root

- `fix_template_response.py` -> project root, next to `main.py`
- `pytest.ini` -> replace current `pytest.ini`
- `.github/workflows/ci.yml` -> exactly this path

## 2. Remove Starlette TemplateResponse warnings

From PowerShell in project root:

```powershell
python fix_template_response.py
poetry run pytest -v
```

Expected result: 82 passed and no TemplateResponse DeprecationWarning.

The script only changes old Jinja calls of this form:

```python
templates.TemplateResponse("page.html", {"request": request})
```

into the new Starlette order with `request` as the first parameter.

After tests are green, the one-time script can be removed:

```powershell
Remove-Item fix_template_response.py
```

## 3. Commit and push CI

```powershell
git add .
git commit -m "ci: add pytest GitHub Actions workflow"
git push
```

GitHub Actions will run automatically on pushes to `main`/`master` and on pull requests.
