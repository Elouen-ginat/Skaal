# Python API Reference

Skaal exposes two related Python surfaces:

- the public package API you use inside application code
- the CLI-parity `skaal.api` namespace you use for in-process planning, building, deploying, and runtime orchestration

This reference is split by submodule so you can jump directly to the slice you need instead of paging through one very long document.

<div class="skaal-example-grid">
	<section class="skaal-example-card">
		<div>
			<h3>Core and Decorators</h3>
			<p><code>skaal.app</code>, <code>skaal.module</code>, <code>skaal.decorators</code>, and <code>skaal.sync</code>.</p>
			<div class="skaal-example-links">
				<a href="python-api-core/">Open reference</a>
			</div>
		</div>
	</section>
	<section class="skaal-example-card">
		<div>
			<h3>Data Surfaces</h3>
			<p><code>skaal.storage</code>, <code>skaal.blob</code>, <code>skaal.vector</code>, <code>skaal.relational</code>, and <code>skaal.channel</code>.</p>
			<div class="skaal-example-links">
				<a href="python-api-data/">Open reference</a>
			</div>
		</div>
	</section>
	<section class="skaal-example-card">
		<div>
			<h3>Patterns and Agents</h3>
			<p><code>skaal.agent</code>, <code>skaal.patterns</code>, and the workflow primitives layered on top of them.</p>
			<div class="skaal-example-links">
				<a href="python-api-patterns/">Open reference</a>
			</div>
		</div>
	</section>
	<section class="skaal-example-card">
		<div>
			<h3>Components and Scheduling</h3>
			<p><code>skaal.components</code>, <code>skaal.schedule</code>, and <code>skaal.secrets</code>.</p>
			<div class="skaal-example-links">
				<a href="python-api-components/">Open reference</a>
			</div>
		</div>
	</section>
	<section class="skaal-example-card">
		<div>
			<h3>CLI-Parity API</h3>
			<p><code>skaal.api</code> and <code>skaal.settings</code> for in-process equivalents of the command line.</p>
			<div class="skaal-example-links">
				<a href="python-api-cli-parity/">Open reference</a>
			</div>
		</div>
	</section>
	<section class="skaal-example-card">
		<div>
			<h3>Types and Policies</h3>
			<p><code>skaal.types</code> plus the retry, rate-limit, migration, and pagination structures used across the package.</p>
			<div class="skaal-example-links">
				<a href="python-api-types/">Open reference</a>
			</div>
		</div>
	</section>
</div>

## Recommended Paths

- If you are writing app code, start with [Core and Decorators](python-api-core.md) and [Data Surfaces](python-api-data.md).
- If you are driving Skaal from scripts or tests, start with [CLI-Parity API](python-api-cli-parity.md).
- If you need policy objects like `RetryPolicy`, `CircuitBreaker`, or migration result types, start with [Types and Policies](python-api-types.md).
