# Johan fork of Aider

Форк [Aider-AI/aider](https://github.com/Aider-AI/aider) для JAE (`apps/jae` в johan-systems).

- Рабочая ветка: `johan`. Апстрим: ветка `upstream-main` (зеркало `Aider-AI/aider` main).
- Теги: `vX.Y.Z+johan.N`, только через `+` (setuptools_scm не парсит `-johan`).
- JAE ставит пакет одной строкой в `apps/jae/aider_install.txt`:
  `aider-chat @ git+https://github.com/sharifzoda4156-ops/aider.git@v0.86.2+johan.1`

## Как брать апстрим

```bash
git remote add upstream https://github.com/Aider-AI/aider.git
git fetch upstream --tags
git log --oneline johan..upstream/main      # что нового
git cherry-pick -x <sha>                    # только нужное
```

Наши собственные правки — отдельные коммиты с префиксом `johan:`.

## Релиз

1. PR в `johan`, CI зелёный (`tests/basic` + `johan/jae_smoke.py`).
2. Тег `vX.Y.Z+johan.N` на мерж-коммите.
3. PR в johan-systems: поменять тег в `aider_install.txt`, self-тесты JAE зелёные.

## Отличия от v0.86.2

- Черри-пики `c0ab7537`, `c0839cf3`, `55164933`: убраны устаревшие модели из тестов (апстримные тесты на 0.86.2 падали).
- Удалены апстримные release/docker/pages/schedule-workflow, добавлен `johan-ci.yml`.
- `johan/jae_smoke.py` — сборка Coder как в JAE без LLM.
- Черри-пик `975e5a89`: Python 3.13/3.14 (`requires-python <3.15`, numpy 2.x / scipy 1.16+ на Python ≥3.11). CI гоняет 3.12 и 3.13.

## Наши улучшения

- **Режим `search`** (`aider/coders/search_coder.py`). Модель сама ищет файлы для правки:
  `SEARCH: <regex>` по содержимому и `READ: <path>[:a-b]` по строкам, в цикле до 8 раундов,
  затем отвечает списком `FILES:`. Только чтение и только git-tracked файлы внутри репо
  (симлинки наружу не читаются), без shell. Итог — `coder.search_files` и `coder.abs_fnames`.
  Использование: `Coder.create(..., edit_format="search")`, `coder.run(запрос)`, потом
  обычный Coder правок с `fnames=coder.search_files`.
