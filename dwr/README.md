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

Once the dependencies are installed, you can also "activate" the virtual environment in a bash terminal by running

```bash
source .venv/bin/activate
```

or in PowerShell by running

```bash
.venv/Scripts/activate.ps1
```

3. Add Python dependencies

All the packages required to run the tool are listed under `project.dependencies` in the `pyproject.toml` file. To add another package to the `pyproject.toml` file, run:

```bash
uv add [package]
```

#### Troubleshooting installation errors:

If you are connected to the DWR network and working behind the DWR firewall, you may get errors installing packages with `uv`. In this case, the work around is to disconnect from ivanti VPN if you are remote or connect to the guest network if you are on site and try again. Once packages are installed, you may reconnect to the DWR network.

### 4. Run the tool

At this point, all project dependencies should be installed. Running the tool is as simple as executing 1 command from within the `dwr` directory:

```bash
uv run -m shiny run main.py
```

This will start the tool as a local server. To access the tool at the default port, navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000). See `uv run -m shiny run --help` for additional, optional CLI arguments.

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

## Azure deployment information

1. Generate `requirements.txt` with uv

```bash
  uv export --format requirements.txt > requirements.txt
```

2. Note that the app's entrypoint is `main.py` in this folder.

## Adding a new outlier detection test

1. Start by adding a function to `od_core.py`. This function is expected to take, as input, a pandas Series
   object along with any test arguments. It is also expected to output a new Series with boolean values where
   True indicates a test failure.
2. Register the test with the UI by updating the `OD_IMPLEMENTED` object in `od.py`. This object bridges the
   gap between the core outlier detection functions and the user interface. After it has been updated, the UI will
   automatically add the new test to the list of possible tests to run.
