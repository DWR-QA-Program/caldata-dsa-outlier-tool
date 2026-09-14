# gunicorn_config.py
# Used by Azure App Service startup command:
#   gunicorn -c gunicorn_config.py --chdir dwr main:app

bind = "0.0.0.0:8000"
workers = 1                          # keep at 1; Shiny sessions are stateful
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 600                        # prevent worker timeout on slow cold starts
accesslog = "-"                      # stdout
errorlog = "-"                       # stderr
loglevel = "info"
