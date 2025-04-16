## Setup

Your python environment manager will be assumed to be some flavor of Anaconda. Some additional info can be found [here](https://cagov.github.io/data-infrastructure/code/local-setup/#1-set-up-a-python-virtual-environment).

### 1. Virtual environment setup
1. Create a new environment (named `dwr`, for example) and get `poetry` set up:
    ```bash
    conda create -n dwr -c conda-forge python=3.10 poetry
    ```
    The following prompt will appear, "_The following NEW packages will be INSTALLED:_ "
    You'll have the option to accept or reject by typing _y_ or _n_. Type _y_ to continue.
2. Activate your virtual environment:
    `conda activate dwr`

### 2. Install Dependencies

1. Make sure your current directory is the top-level project directory (i.e. the one with `pyproject.toml`)

2. Install dependencies with poetry
    ```bash
    poetry install --with dev --no-root
    ```

### 3. Running the tool

At this point, all project dependencies should be installed. Running the tool is as simple as executing 1 command from within the `app` directory:

```bash
shiny run app.py
```

This will start the tool as a local server. To access the tool at the default port, navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000). See `shiny run --help` for additional, optional CLI arguments.
