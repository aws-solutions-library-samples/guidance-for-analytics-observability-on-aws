import re
from aws_cdk import App, Aspects
from aws_cdk.assertions import Annotations, Template
from infra.backend_stack import BackendStack
from cdk_nag import AwsSolutionsChecks

app = App()
app.node.set_context("TshirtSize", "L")
app.node.set_context("VpcID", "vpc-0fb408d38ca0ddcdf")
stack = BackendStack(app, "NagTestBackend", env={'region': 'us-east-1', 'account': '11111111111111'})


# Simple rule informational messages
Aspects.of(stack).add(AwsSolutionsChecks())

template = Template.from_stack(stack)

warnings = Annotations.from_stack(stack).find_warning('*', '*')
print(warnings)
assert len(warnings) == 0

errors = Annotations.from_stack(stack).find_error('*', '*')
print(errors)
assert len(errors) == 0

