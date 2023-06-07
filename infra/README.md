
# CDK application for the infrastructure used by the AWS Analytics Observability

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize or deploy the CloudFormation template for this code.

```
$ cdk synth -c TshirtSize=xs
$ cdk deploy -c TshirtSize=xs
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.


## Create the ingestion pipeline

Use the `pipeline.yaml` file to configure an ingestion pipeline in Opensearch service console. 
Change the parameters to point to your infrastructure

## TODO

Add domain monitoring and indices permissions to avoid this issue
```
{"error":{"root_cause":[{"type":"security_exception","reason":"no permissions for [cluster:monitor/health] and User [name=arn:aws:iam::099713751195:role/gromav, backend_roles=[arn:aws:iam::099713751195:role/gromav], requestedTenant=null]"}],"type":"security_exception","reason":"no permissions for [cluster:monitor/health] and User [name=arn:aws:iam::099713751195:role/gromav, backend_roles=[arn:aws:iam::099713751195:role/gromav], requestedTenant=null]"},"status":403}
```