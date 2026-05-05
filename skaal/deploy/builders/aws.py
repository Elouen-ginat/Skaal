"""AWS Lambda Pulumi stack builder."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from skaal.deploy.backends import get_handler
from skaal.deploy.builders.apigw import add_aws_apigw_resources
from skaal.deploy.builders.common import app_has_jobs, database_name, resource_slug
from skaal.deploy.config import DynamoDBDeployConfig, LambdaDeployConfig, RDSPostgresDeployConfig
from skaal.deploy.secrets import AwsSecretInjector
from skaal.types import AppLike, PulumiStack

if TYPE_CHECKING:
    from skaal.plan import PlanFile


_LAMBDA_BASIC_EXEC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
_LAMBDA_VPC_EXEC_POLICY = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
_DYNAMODB_ACTIONS = [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:DeleteItem",
    "dynamodb:Scan",
    "dynamodb:Query",
]
_S3_ACTIONS = [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:ListBucket",
]
_LAMBDA_INVOKE_ACTIONS = ["lambda:InvokeFunction"]


def build_pulumi_stack(app: AppLike, plan: "PlanFile", region: str = "us-east-1") -> PulumiStack:
    has_jobs = app_has_jobs(app)
    deploy = LambdaDeployConfig.model_validate(plan.deploy_config)
    config: dict[str, Any] = {
        "aws:region": {"type": "string", "default": region},
        "lambdaMemoryMb": {"type": "integer", "default": deploy.memory_mb},
        "lambdaTimeout": {"type": "integer", "default": deploy.timeout},
        "lambdaRuntime": {"type": "string", "default": deploy.runtime},
        "lambdaArchitecture": {"type": "string", "default": deploy.architecture},
    }
    if has_jobs:
        config["jobsWorkerMaxBursts"] = {"type": "integer", "default": 5}
        config["jobsWorkerMaxJobs"] = {"type": "integer", "default": 10}
        config["jobsRedisNodeType"] = {"type": "string", "default": "cache.t4g.micro"}

    variables: dict[str, Any] = {}
    resources: dict[str, Any] = {}
    env_vars: dict[str, str] = {}
    table_outputs: dict[str, str] = {}
    bucket_outputs: dict[str, str] = {}
    db_outputs: dict[str, str] = {}
    has_dynamodb = any(spec.backend == "dynamodb" for spec in plan.storage.values())
    has_s3 = any(spec.backend == "s3" for spec in plan.storage.values())
    needs_vpc = any(get_handler(spec).requires_vpc for spec in plan.storage.values()) or has_jobs
    s3_bucket_keys: list[str] = []

    if needs_vpc:
        variables["defaultVpcId"] = {
            "fn::invoke": {
                "function": "aws:ec2:getVpc",
                "arguments": {"default": True},
                "return": "id",
            }
        }
        variables["defaultSubnetIds"] = {
            "fn::invoke": {
                "function": "aws:ec2:getSubnets",
                "arguments": {"filters": [{"name": "vpc-id", "values": ["${defaultVpcId}"]}]},
                "return": "ids",
            }
        }
        resources["lambda-sg"] = {
            "type": "aws:ec2:SecurityGroup",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-lambda",
                "description": "Lambda security group for Skaal app access to VPC resources",
                "vpcId": "${defaultVpcId}",
                "egress": [
                    {
                        "protocol": "-1",
                        "fromPort": 0,
                        "toPort": 0,
                        "cidrBlocks": ["0.0.0.0/0"],
                    }
                ],
                "tags": {"skaal-app": app.name},
            },
        }

    if has_jobs:
        resources["jobs-redis-subnet-group"] = {
            "type": "aws:elasticache:SubnetGroup",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-jobs",
                "subnetIds": "${defaultSubnetIds}",
                "description": f"Redis subnet group for Skaal jobs on {app.name}",
            },
        }
        resources["jobs-redis-sg"] = {
            "type": "aws:ec2:SecurityGroup",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-jobs-redis",
                "description": "Redis access for Skaal background jobs",
                "vpcId": "${defaultVpcId}",
                "ingress": [
                    {
                        "protocol": "tcp",
                        "fromPort": 6379,
                        "toPort": 6379,
                        "securityGroups": ["${lambda-sg.id}"],
                    }
                ],
                "egress": [
                    {
                        "protocol": "-1",
                        "fromPort": 0,
                        "toPort": 0,
                        "cidrBlocks": ["0.0.0.0/0"],
                    }
                ],
                "tags": {"skaal-app": app.name, "skaal-component": "jobs-redis"},
            },
        }
        resources["jobs-redis"] = {
            "type": "aws:elasticache:ReplicationGroup",
            "properties": {
                "replicationGroupId": f"${{pulumi.stack}}-{resource_slug(app.name, max_len=20)}-jobs",
                "description": f"Background jobs Redis for {app.name}",
                "engine": "redis",
                "engineVersion": "7.1",
                "nodeType": "${jobsRedisNodeType}",
                "numCacheClusters": 1,
                "port": 6379,
                "subnetGroupName": "${jobs-redis-subnet-group.name}",
                "securityGroupIds": ["${jobs-redis-sg.id}"],
                "atRestEncryptionEnabled": True,
                "transitEncryptionEnabled": False,
                "tags": {"skaal-app": app.name, "skaal-component": "jobs-redis"},
            },
        }
        env_vars["SKAAL_JOBS_REDIS_URL"] = "redis://${jobs-redis.primaryEndpointAddress}:6379"

    for qualified_name, spec in plan.storage.items():
        class_name = qualified_name.split(".")[-1]
        handler = get_handler(spec)
        env_var = f"{handler.env_prefix}_{class_name.upper()}" if handler.env_prefix else ""
        slug = resource_slug(class_name)

        if spec.backend == "s3":
            resource_key = f"{slug}-bucket"
            bucket_name = f"${{pulumi.stack}}-{slug}"
            resources[resource_key] = {
                "type": "aws:s3:BucketV2",
                "properties": {
                    "bucket": bucket_name,
                    "tags": {"skaal-app": app.name, "skaal-storage": qualified_name},
                },
            }
            env_vars[env_var] = bucket_name
            bucket_outputs[class_name.lower()] = bucket_name
            s3_bucket_keys.append(resource_key)
            continue

        if spec.backend == "dynamodb":
            resource_key = f"{slug}-table"
            dynamodb_config = DynamoDBDeployConfig.model_validate(spec.deploy_params)
            resources[resource_key] = {
                "type": "aws:dynamodb:Table",
                "properties": {
                    "name": f"${{pulumi.stack}}-{slug}",
                    "hashKey": dynamodb_config.hash_key,
                    "billingMode": dynamodb_config.billing_mode,
                    "attributes": [
                        {"name": dynamodb_config.hash_key, "type": dynamodb_config.hash_key_type}
                    ],
                    "tags": {"skaal-app": app.name, "skaal-storage": qualified_name},
                },
            }
            env_vars[env_var] = f"${{{resource_key}.name}}"
            table_outputs[class_name.lower()] = f"${{{resource_key}.name}}"
            continue

        if spec.backend in ("rds-postgres", "rds-pgvector"):
            postgres_config = RDSPostgresDeployConfig.model_validate(spec.deploy_params)
            config[f"dbInstanceClass{class_name}"] = {
                "type": "string",
                "default": postgres_config.instance_class,
            }
            config[f"dbAllocatedStorageGb{class_name}"] = {
                "type": "integer",
                "default": postgres_config.allocated_storage_gb,
            }
            config[f"dbMaxAllocatedStorageGb{class_name}"] = {
                "type": "integer",
                "default": postgres_config.max_allocated_storage_gb,
            }
            config[f"dbDeletionProtection{class_name}"] = {
                "type": "boolean",
                "default": postgres_config.deletion_protection,
            }

            password_key = f"{slug}-db-password"
            security_group_key = f"{slug}-db-sg"
            db_key = f"{slug}-db"
            db_name = database_name(app.name)

            resources[password_key] = {
                "type": "random:index:RandomPassword",
                "properties": {
                    "length": 24,
                    "special": False,
                    "upper": True,
                    "lower": True,
                    "numeric": True,
                },
            }
            resources[security_group_key] = {
                "type": "aws:ec2:SecurityGroup",
                "properties": {
                    "name": f"${{pulumi.stack}}-{slug}-db",
                    "description": f"Postgres access for {class_name}",
                    "vpcId": "${defaultVpcId}",
                    "ingress": [
                        {
                            "protocol": "tcp",
                            "fromPort": postgres_config.port,
                            "toPort": postgres_config.port,
                            "securityGroups": ["${lambda-sg.id}"],
                        }
                    ],
                    "egress": [
                        {
                            "protocol": "-1",
                            "fromPort": 0,
                            "toPort": 0,
                            "cidrBlocks": ["0.0.0.0/0"],
                        }
                    ],
                    "tags": {"skaal-app": app.name, "skaal-storage": qualified_name},
                },
            }
            resources[db_key] = {
                "type": "aws:rds:Instance",
                "properties": {
                    "identifier": f"${{pulumi.stack}}-{slug}",
                    "dbName": db_name,
                    "engine": "postgres",
                    "engineVersion": postgres_config.engine_version,
                    "instanceClass": f"${{{f'dbInstanceClass{class_name}'}}}",
                    "allocatedStorage": f"${{{f'dbAllocatedStorageGb{class_name}'}}}",
                    "maxAllocatedStorage": f"${{{f'dbMaxAllocatedStorageGb{class_name}'}}}",
                    "storageType": postgres_config.storage_type,
                    "backupRetentionPeriod": postgres_config.backup_retention_days,
                    "deletionProtection": f"${{{f'dbDeletionProtection{class_name}'}}}",
                    "username": postgres_config.username,
                    "password": f"${{{password_key}.result}}",
                    "port": postgres_config.port,
                    "manageMasterUserPassword": False,
                    "publiclyAccessible": False,
                    "skipFinalSnapshot": True,
                    "storageEncrypted": True,
                    "applyImmediately": True,
                    "vpcSecurityGroupIds": [f"${{{security_group_key}.id}}"],
                    "tags": {"skaal-app": app.name, "skaal-storage": qualified_name},
                },
            }
            env_vars[env_var] = (
                f"postgresql://{postgres_config.username}:${{{password_key}.result}}"
                f"@${{{db_key}.address}}:{postgres_config.port}/{db_name}"
            )
            db_outputs[class_name.lower()] = f"${{{db_key}.address}}"
            continue

        raise ValueError(
            f"AWS deploy target does not yet support provisioning backend {spec.backend!r} for {qualified_name!r}."
        )

    secret_injector = AwsSecretInjector()
    for name, source in secret_injector.env_vars(plan).items():
        env_vars.setdefault(name, source)
    secret_iam_statements = secret_injector.iam_statements(plan)

    resources["lambda-role"] = {
        "type": "aws:iam:Role",
        "properties": {
            "name": f"${{pulumi.stack}}-{app.name}-role",
            "assumeRolePolicy": {
                "fn::toJSON": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            },
        },
    }
    resources["lambda-basic-exec"] = {
        "type": "aws:iam:RolePolicyAttachment",
        "properties": {"role": "${lambda-role.name}", "policyArn": _LAMBDA_BASIC_EXEC_POLICY},
    }
    lambda_depends_on = ["${lambda-basic-exec}"]

    if has_dynamodb:
        resources["dynamodb-policy"] = {
            "type": "aws:iam:Policy",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-dynamodb",
                "policy": {
                    "fn::toJSON": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": _DYNAMODB_ACTIONS, "Resource": "*"}
                        ],
                    }
                },
            },
        }
        resources["lambda-dynamodb-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {"role": "${lambda-role.name}", "policyArn": "${dynamodb-policy.arn}"},
        }
        lambda_depends_on.append("${lambda-dynamodb-attach}")

    if has_s3:
        bucket_resources: list[str] = []
        for bucket_key in s3_bucket_keys:
            bucket_resources.append(f"${{{bucket_key}.arn}}")
            bucket_resources.append(f"${{{bucket_key}.arn}}/*")
        resources["s3-policy"] = {
            "type": "aws:iam:Policy",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-s3",
                "policy": {
                    "fn::toJSON": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": _S3_ACTIONS, "Resource": bucket_resources}
                        ],
                    }
                },
            },
        }
        resources["lambda-s3-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {"role": "${lambda-role.name}", "policyArn": "${s3-policy.arn}"},
        }
        lambda_depends_on.append("${lambda-s3-attach}")

    if needs_vpc:
        resources["lambda-vpc-access-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {"role": "${lambda-role.name}", "policyArn": _LAMBDA_VPC_EXEC_POLICY},
        }
        lambda_depends_on.append("${lambda-vpc-access-attach}")

    if secret_iam_statements:
        resources["secrets-policy"] = {
            "type": "aws:iam:Policy",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-secrets",
                "policy": {
                    "fn::toJSON": {
                        "Version": "2012-10-17",
                        "Statement": secret_iam_statements,
                    }
                },
            },
        }
        resources["lambda-secrets-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {
                "role": "${lambda-role.name}",
                "policyArn": "${secrets-policy.arn}",
            },
        }
        lambda_depends_on.append("${lambda-secrets-attach}")

    if has_jobs:
        resources["jobs-worker-invoke-policy"] = {
            "type": "aws:iam:Policy",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-jobs-worker-invoke",
                "policy": {
                    "fn::toJSON": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": _LAMBDA_INVOKE_ACTIONS,
                                "Resource": "${jobs-worker-fn.arn}",
                            }
                        ],
                    }
                },
            },
        }
        resources["jobs-worker-invoke-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {
                "role": "${lambda-role.name}",
                "policyArn": "${jobs-worker-invoke-policy.arn}",
            },
        }
        lambda_depends_on.append("${jobs-worker-invoke-attach}")

    lambda_props: dict[str, Any] = {
        "name": f"${{pulumi.stack}}-{app.name}",
        "runtime": "${lambdaRuntime}",
        "architectures": ["${lambdaArchitecture}"],
        "handler": "handler.handler",
        "role": "${lambda-role.arn}",
        "code": {"fn::fileArchive": "./lambda_package"},
        "timeout": "${lambdaTimeout}",
        "memorySize": "${lambdaMemoryMb}",
        "environment": {"variables": env_vars},
    }
    if has_jobs:
        lambda_props["environment"]["variables"]["SKAAL_JOBS_WORKER_FUNCTION"] = (
            "${jobs-worker-fn.name}"
        )
    if needs_vpc:
        lambda_props["vpcConfig"] = {
            "subnetIds": "${defaultSubnetIds}",
            "securityGroupIds": ["${lambda-sg.id}"],
            "vpcId": "${defaultVpcId}",
        }
    if deploy.reserved_concurrency >= 0:
        lambda_props["reservedConcurrentExecutions"] = "${lambdaReservedConcurrency}"
        config["lambdaReservedConcurrency"] = {
            "type": "integer",
            "default": deploy.reserved_concurrency,
        }

    resources["lambda-fn"] = {
        "type": "aws:lambda:Function",
        "properties": lambda_props,
        "options": {"dependsOn": lambda_depends_on},
    }

    if has_jobs:
        worker_env_vars = dict(env_vars)
        worker_env_vars["SKAAL_JOBS_WORKER_MAX_BURSTS"] = "${jobsWorkerMaxBursts}"
        worker_env_vars["SKAAL_JOBS_WORKER_MAX_JOBS"] = "${jobsWorkerMaxJobs}"
        worker_props: dict[str, Any] = {
            "name": f"${{pulumi.stack}}-{app.name}-jobs-worker",
            "runtime": "${lambdaRuntime}",
            "architectures": ["${lambdaArchitecture}"],
            "handler": "worker.handler",
            "role": "${lambda-role.arn}",
            "code": {"fn::fileArchive": "./lambda_package"},
            "timeout": "${lambdaTimeout}",
            "memorySize": "${lambdaMemoryMb}",
            "environment": {"variables": worker_env_vars},
        }
        if needs_vpc:
            worker_props["vpcConfig"] = {
                "subnetIds": "${defaultSubnetIds}",
                "securityGroupIds": ["${lambda-sg.id}"],
                "vpcId": "${defaultVpcId}",
            }
        resources["jobs-worker-fn"] = {
            "type": "aws:lambda:Function",
            "properties": worker_props,
            "options": {"dependsOn": lambda_depends_on + ["${jobs-redis}"]},
        }
        resources["jobs-worker-rule"] = {
            "type": "aws:events:Rule",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-jobs-worker",
                "scheduleExpression": "rate(1 minute)",
                "isEnabled": True,
            },
            "options": {"dependsOn": ["${jobs-worker-fn}"]},
        }
        resources["jobs-worker-target"] = {
            "type": "aws:events:Target",
            "properties": {
                "rule": "${jobs-worker-rule.name}",
                "arn": "${jobs-worker-fn.arn}",
                "input": json.dumps({"_skaal_jobs_worker": True}),
            },
        }
        resources["jobs-worker-permission"] = {
            "type": "aws:lambda:Permission",
            "properties": {
                "action": "lambda:InvokeFunction",
                "function": "${jobs-worker-fn.name}",
                "principal": "events.amazonaws.com",
                "sourceArn": "${jobs-worker-rule.arn}",
            },
        }

    add_aws_apigw_resources(app, plan, resources, config)

    for comp_name, comp in plan.components.items():
        if comp.kind != "schedule-trigger":
            continue
        from skaal.types import ScheduleTriggerConfig

        cfg = cast(ScheduleTriggerConfig, comp.config)
        trigger_type = cfg.trigger_type
        target_fn = cfg.target_function

        if trigger_type == "cron":
            from skaal.schedule import Cron

            schedule_expr = Cron(expression=cast(Any, cfg.trigger).expression).as_aws_expression()
        else:
            from skaal.schedule import Every

            schedule_expr = Every(interval=cast(Any, cfg.trigger).interval).as_rate_expression()

        rule_key = f"{comp_name}-rule"
        target_key = f"{comp_name}-target"
        permission_key = f"{comp_name}-permission"

        resources[rule_key] = {
            "type": "aws:events:Rule",
            "properties": {
                "name": f"${{pulumi.stack}}-{comp_name}",
                "scheduleExpression": schedule_expr,
                "isEnabled": True,
            },
            "options": {"dependsOn": ["${lambda-fn}"]},
        }
        resources[target_key] = {
            "type": "aws:events:Target",
            "properties": {
                "rule": f"${{{rule_key}.name}}",
                "arn": "${lambda-fn.arn}",
                "input": json.dumps({"_skaal_trigger": comp_name, "target_function": target_fn}),
            },
        }
        resources[permission_key] = {
            "type": "aws:lambda:Permission",
            "properties": {
                "action": "lambda:InvokeFunction",
                "function": "${lambda-fn.name}",
                "principal": "events.amazonaws.com",
                "sourceArn": f"${{{rule_key}.arn}}",
            },
        }

    if any(component.kind == "schedule-trigger" for component in plan.components.values()):
        resources["events-invoke-policy"] = {
            "type": "aws:iam:Policy",
            "properties": {
                "name": f"${{pulumi.stack}}-{app.name}-events-invoke",
                "policy": {
                    "fn::toJSON": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["lambda:InvokeFunction"],
                                "Resource": "${lambda-fn.arn}",
                            }
                        ],
                    }
                },
            },
        }
        resources["events-invoke-attach"] = {
            "type": "aws:iam:RolePolicyAttachment",
            "properties": {
                "role": "${lambda-role.name}",
                "policyArn": "${events-invoke-policy.arn}",
            },
        }

    outputs: dict[str, str] = {
        "apiUrl": "${default-stage.invokeUrl}",
        "lambdaArn": "${lambda-fn.arn}",
        **({"jobsWorkerArn": "${jobs-worker-fn.arn}"} if has_jobs else {}),
        **{f"bucket{k.capitalize()}": value for k, value in bucket_outputs.items()},
        **{f"table{k.capitalize()}": value for k, value in table_outputs.items()},
        **{f"dbEndpoint{k.capitalize()}": value for k, value in db_outputs.items()},
    }

    stack: PulumiStack = {
        "name": f"skaal-{app.name}",
        "runtime": "yaml",
        "config": config,
        "resources": resources,
        "outputs": outputs,
    }
    if variables:
        stack["variables"] = variables
    return stack
