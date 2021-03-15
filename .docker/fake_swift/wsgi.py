import os
from paste.deploy import loadapp


application = loadapp('config:app.conf', relative_to=os.getcwd())
