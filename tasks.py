import invoke

def run(*args, **kwargs):
    kwargs.update(echo=True)
    return invoke.run(*args, **kwargs)

@invoke.task
def clean():
    run("rm -rf .tox/")
    run("rm -rf dist/")
    run("rm -rf pyservice.egg-info/")
    run("find . -name '*.pyc' -delete")
    run("find . -name '__pycache__' -delete")
    run("rm -f .coverage")

@invoke.task('clean')
def build():
    run("python setup.py develop")
    pass

@invoke.task('clean')
def test():
    run('tox')
