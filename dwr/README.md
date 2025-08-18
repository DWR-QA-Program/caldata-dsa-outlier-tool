## Local server setup

### 1. Install uv

This project uses `uv` for python package and virtual environment management. Installation instructions can be found [here](https://docs.astral.sh/uv/getting-started/installation/).

### 2. Install Python dependencies

If you prefix your commands with uv run (e.g. `uv run shiny run main.py`), then uv will automatically make sure that the appropriate dependencies are installed before invoking the command.

However, if you want to explicitly ensure that all of the dependencies are installed in the virtual environment, run
```bash
uv sync
```
in the root of this repository.

Once the dependencies are installed, you can also "activate" the virtual environment by running
```bash
source .venv/bin/activate
```
from the repository root. With the environment activated, you no longer have to prefix commands with `uv run`.

Which approach to take is largely a matter of personal preference:

- Using the `uv run` prefix is more reliable, as dependencies are always resolved before executing.
- Using `source .venv/bin/activate` involves less typing.


### 3. Run the tool

At this point, all project dependencies should be installed. Running the tool is as simple as executing 1 command from within the `dwr` directory:

```bash
shiny run main.py
```

This will start the tool as a local server. To access the tool at the default port, navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000). See `shiny run --help` for additional, optional CLI arguments.

## Running unit tests

Assuming the above setup steps have been completed, running unit tests will only require executing the `pytest` command. Example output:

```
# pytest
========================================= test session starts =========================================
platform linux -- Python 3.10.16, pytest-8.3.5, pluggy-1.5.0
rootdir: /home/user/subfolder/caldata-dsa-dwr
configfile: pyproject.toml
plugins: anyio-4.9.0, shiny-1.4.0
collected 5 items

tests/test_upload_util.py .....                                                                 [100%]

========================================== 5 passed in 0.38s ==========================================
```
