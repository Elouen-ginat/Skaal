# Comparison

Skaal sits between handwritten infrastructure and a hosted platform. It is for Python teams that want application code to declare the deploy shape without giving up ownership of the deploy output.

## Summary table

| | **Skaal** | **Plain Pulumi** | **Encore / SST** | **Managed PaaS** |
| --- | --- | --- | --- | --- |
| Main language | Python | Any Pulumi language | TypeScript or Go, depending on the tool | Usually app-language specific |
| Primary abstraction | App graph in Python | Infrastructure resources in code | Framework-owned service model | Hosted service configuration |
| Infra choice | Inferred then bound from `skaal.toml` | You choose every resource directly | Framework conventions and cloud-specific abstractions | Chosen by the platform |
| Deploy output | Rendered files you can inspect | Your source of truth | Tool-specific output or hosted control plane | Usually not owned by you |
| Multi-environment story | One app graph, named environments | You model each environment yourself | Good inside the tool's target cloud | Depends on the platform |
| Lock-in | Low to medium | Low | Medium | High |

## Use Skaal when

- You want one Python app graph to drive local and cloud environments.
- You want real deploy artifacts you can inspect and keep.
- You want the data surfaces and the deploy surface to stay in the same codebase.

## Use plain Pulumi when

- You already know the exact resource graph.
- Your team is comfortable writing and maintaining the IaC directly.
- You do not need a framework-owned application model.

## Use Encore or SST when

- Your team is already committed to their language and cloud assumptions.
- You want deeper platform conventions than Skaal provides.
- You are happy to let the framework shape more of the application runtime.

## Use a managed PaaS when

- You want the platform to own most infrastructure choices.
- Fast setup matters more than ownership of the output.
- You accept tighter runtime lock-in.

## What Skaal is not trying to be

- A hosted control plane.
- A replacement for your web framework.
- A replacement for handwritten Pulumi when handwritten Pulumi is already the simplest answer.
