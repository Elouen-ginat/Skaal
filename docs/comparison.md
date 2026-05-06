# How Skaal Compares

Where Skaal sits in the application-framework / infrastructure-as-code landscape, and when another tool is the better pick.

## Summary table

| | **Skaal** | **Encore** | **SST** | **Wing** | **Modal** | **Pulumi (alone)** |
|---|---|---|---|---|---|---|
| Language | Python | Go / TypeScript | TypeScript | Wing DSL | Python | Any (Python, TS, Go, …) |
| Primary abstraction | Constraints solved against a catalog | Resource primitives in code | AWS resource constructs | Cloud-portable DSL | Hosted compute primitives | Imperative IaC |
| Backend selection | Z3 solver picks per environment | Code-defined | Code-defined | Code-defined | Hosted by Modal | Code-defined |
| Multi-cloud | Local + AWS + GCP from one app file | AWS + GCP (platform-managed) | AWS-leaning | Multi-target via compiler | Modal cloud only | Anything Pulumi supports |
| Deploy mechanism | Generated Pulumi programs | Encore platform / self-host | CDK / CloudFormation | Terraform / CDK targets | Modal runtime | Pulumi |
| Local dev parity | Yes (local catalog mirrors prod constraints) | Yes (local runner) | Partial (LiveLambda) | Yes (sim) | No (cloud-only) | N/A |
| Lock-in | Eject anytime; generated artifacts are yours | Platform-coupled when hosted | AWS-coupled | Compiler-coupled | Modal-coupled | None |
| License | GPL-3.0-or-later | MPL-2.0 | MIT | MIT | Proprietary (hosted) | Apache-2.0 |

## When Skaal wins

- You want **one application file** to deploy to local, AWS, and GCP, and you'd rather describe a backend's *behavior* than name it.
- You care about **auditable backend selection** — a `plan.skaal.lock` that lists rejected candidates with reasons beats a hidden default.
- You want to **swap backends by editing a TOML catalog**, not by refactoring code.
- You're building several similar Python services and don't want to copy-paste Pulumi between them.

## When Encore is a better pick

You want a managed backend platform with built-in tracing, secrets, and a hosted control plane, and you're comfortable on Encore's runtime. Encore goes further than Skaal on day-2 operations; Skaal goes further on backend selection and ejection.

## When SST is a better pick

You're TypeScript-first, AWS-only, and you want tight CDK integration with LiveLambda for fast inner-loop dev. Skaal doesn't compete in the TypeScript ecosystem.

## When Wing is a better pick

You're willing to adopt a new language to get cloud-portable primitives at the type-system level, and your team can absorb that learning curve. Wing's compiler-driven approach is more ambitious than Skaal's solver; Skaal is the pragmatic Python answer in the same problem space.

## When Modal is a better pick

You want a hosted Python compute platform with zero infra to run, and you accept Modal as the deployment target. Modal is a hosted runtime; Skaal generates open infrastructure you own.

## When plain Pulumi is a better pick

You have **one target, one backend choice per resource, and a stable architecture**. Skaal's solver pays for itself when the catalog has alternatives or when environments diverge — if neither is true, plain Pulumi (or Terraform / CDK) is simpler.

## What Skaal is *not* trying to be

- A **hosted platform.** No control plane, no billing surface, no proprietary runtime. The artifacts are yours.
- A **multi-language framework.** Python only. Cross-language plumbing is out of scope.
- A **Kubernetes operator.** K8s is a possible deploy target, not the model.
- A **replacement for Pulumi.** Skaal *generates* Pulumi; if you'd rather write it by hand, do.
