Python Jenkins client
====================

jenkinsc is a client library for Jenkins API that is made to handle all the possible connectivity and Jenkins API issues

## Installation

```
pip install jenkinsc
```

## How to use

Here an example of usage:

```    
jenkins = Jenkins('environ['JENKINS_URL']', username=environ['JENKINS_USR'], password=environ['JENKINS_PWD'])
jenkins['JOBNAME'].build(build_params={'SRC': 'myscr/folder', 'VERSION': '111'})  # Non blocking jenkins job call
queue_item = jenkins['JOBNAME2'].build(build_params={'REDEPLOY': 'true', 'VERSION': '111'}, block=True)  # will wait till the job is finished 

if not queue_item.get_build().successful():
    raise Exception('JOB2 failed')
```

## How to deploy
jenkinsc is deployed automatically on adding new tag. 
To make a new release just add a tag on master after upgrading package version in `setup.py`.

#### How to add a tag
Example: 
```
git tag -a v0.0.37 -m "Version 0.0.37"
git push --tag
```
