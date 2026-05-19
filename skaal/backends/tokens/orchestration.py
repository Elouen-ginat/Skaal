"""Schedule and job backend tokens."""

from skaal.backends._base import Backend


class Apscheduler(Backend[object]):
    name = "apscheduler"
    kinds = frozenset({"schedule"})


class EventBridgeLambda(Backend[object]):
    name = "eventbridge-lambda"
    kinds = frozenset({"schedule"})


class CloudSchedulerCloudRun(Backend[object]):
    name = "cloud-scheduler-run"
    kinds = frozenset({"schedule"})


class SqsLambdaWorker(Backend[object]):
    name = "sqs-lambda-worker"
    kinds = frozenset({"job"})


class CloudTasksCloudRun(Backend[object]):
    name = "cloud-tasks-run"
    kinds = frozenset({"job"})


__all__ = [
    "Apscheduler",
    "CloudSchedulerCloudRun",
    "CloudTasksCloudRun",
    "EventBridgeLambda",
    "SqsLambdaWorker",
]
