# When to use Skaal

Skaal is for teams that want one Python app graph to drive local and cloud environments without handing over ownership of the deploy output.

![Cloud route illustration](assets/graphics/illustrations/cloud-route.svg)

## Decision table

| Use Skaal | Use plain Pulumi | Use a managed PaaS |
| --- | --- | --- |
| You want typed app primitives and deploy output in one codebase. | You already know the exact resource graph. | You want the platform to own most runtime and infra choices. |
| You want real artifacts you can inspect and keep. | Your team is comfortable writing IaC directly. | Speed matters more than ownership of the output. |
| You want one app graph to target local and cloud environments. | One target and one backend choice per resource is enough. | You accept higher lock-in for a simpler setup. |

## Use Skaal when

- your application model and your infrastructure model should live together
- you want mounted FastAPI or Starlette, not a framework-owned HTTP abstraction
- you want generated Pulumi output instead of a hosted control plane

## Do not use Skaal when

- handwritten Pulumi is already simple enough
- you need a fully polished scaffolder and every auxiliary CLI command today
- you want the platform to hide the deployment details from your team

## The honest trade

Skaal gives you a coherent app-to-deploy pipeline. In return, you adopt its primitives, environment file, and deploy flow. That is a good trade when you want code-first infrastructure. It is unnecessary when direct IaC already fits.

## Next

- Read [Comparison](comparison.md) for the tool-by-tool view.
- Read [What you can build](platform-features.md) if you want concrete app shapes.
