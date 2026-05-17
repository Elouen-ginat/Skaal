---
hide:
  - navigation
  - toc
---

<section class="lp-hero">
    <div class="lp-hero__copy">
        <div class="lp-kicker"><span class="lp-kicker__pulse"></span>code-first infrastructure for Python</div>
        <h1 id="skaal" class="lp-hero__h1">Ship the app you wrote. <em>Keep</em> the infrastructure you own.</h1>
        <p class="lp-hero__lead">Declare <code>Store</code>, <code>Table</code>, <code>BlobStore</code>, <code>Topic</code>, exposed functions, and mounted HTTP in Python. Skaal infers the blueprint, binds it to one environment from <code>skaal.toml</code>, and renders deploy output you can inspect.</p>
        <div class="lp-hero__actions">
            <a class="sk-btn sk-btn--primary" href="getting-started/">Get started</a>
            <a class="sk-btn sk-btn--ghost" href="tutorials/">Follow the tutorial track</a>
            <a class="sk-btn sk-btn--ghost" href="comparison/">See the trade-offs</a>
        </div>
        <div class="lp-hero__meta">
            <span>typed clients at the call site</span>
            <span>real Pulumi output on disk</span>
            <span>one app graph across local and cloud environments</span>
        </div>
    </div>
    <div class="lp-hero__visual">
        <div class="lp-codecard">
            <div class="lp-codecard__head">
                <div class="lp-codecard__dots"><i></i><i></i><i></i></div>
                <span class="lp-codecard__file">billing/app.py</span>
                <span class="lp-codecard__lang">python</span>
            </div>
            <pre class="lp-codecard__body"><span class="kw">from</span> skaal <span class="kw">import</span> <span class="cls">App</span>, <span class="cls">Store</span>, <span class="cls">Topic</span>

app = <span class="cls">App</span>(<span class="str">"billing"</span>)

<span class="deco">@app.storage</span>
<span class="kw">class</span> <span class="cls">Users</span>(<span class="cls">Store</span>[<span class="cls">User</span>]):
        ...

<span class="deco">@app.expose()</span>
<span class="kw">async def</span> signup(user: <span class="cls">User</span>) -&gt; <span class="cls">User</span>:
        <span class="kw">await</span> Users.set(user.id, user)
        <span class="kw">return</span> user</pre>
        </div>
        <div class="lp-flowarrow">
            <span class="lp-flowarrow__dot"></span>
            <span>bind for prod</span>
            <span class="lp-flowarrow__line"></span>
        </div>
        <div class="lp-plancard">
            <div class="lp-plancard__head">
                <h4>Bound plan</h4>
                <span class="sk-sig sk-sig--resolved"><span class="sk-sig__dot"></span>ready</span>
            </div>
            <div class="lp-plancard__body">
                <div class="lp-plancard__title-row">
                    <h4>examples.todo_api</h4>
                    <span>env=prod</span>
                </div>
                <div class="lp-bcand is-selected">
                    <span class="lp-bcand__name">Todos -&gt; dynamodb</span>
                    <span class="lp-bcand__cost">aws</span>
                    <span class="lp-bcand__tag">bound</span>
                </div>
                <div class="lp-bcand is-selected">
                    <span class="lp-bcand__name">Comments -&gt; postgres</span>
                    <span class="lp-bcand__cost">aws</span>
                    <span class="lp-bcand__tag">bound</span>
                </div>
                <div class="lp-bcand is-selected">
                    <span class="lp-bcand__name">Uploads -&gt; s3</span>
                    <span class="lp-bcand__cost">aws</span>
                    <span class="lp-bcand__tag">bound</span>
                </div>
                <div class="lp-bcand is-rejected">
                    <span class="lp-bcand__name">local sqlite fallback</span>
                    <span class="lp-bcand__cost">local</span>
                    <span class="lp-bcand__tag">other env</span>
                </div>
            </div>
        </div>
    </div>
</section>

<div class="lp-installstrip">
    <span class="lp-installstrip__lbl">fastest path</span>
    <div class="lp-installstrip__items">
        <span><code>pip install "skaal[serve]"</code></span>
        <span><code>skaal run examples.counter:app</code></span>
        <span><code>skaal build examples.todo_api:app --env prod</code></span>
        <span><code>skaal deploy examples.todo_api:app --env prod</code></span>
    </div>
</div>

<nav class="lp-quicknav" aria-label="Homepage shortcuts">
    <a class="lp-quicknav__link" href="#how-it-lands">how it lands</a>
    <a class="lp-quicknav__link" href="#environment-loop">environment loop</a>
    <a class="lp-quicknav__link" href="#command-surface">command surface</a>
    <a class="lp-quicknav__link" href="#what-you-can-ship">what you can ship</a>
</nav>

<section class="lp-section" id="how-it-lands">
    <div class="lp-section__intro">
        <div class="lp-eyebrow">What Skaal does</div>
        <div class="lp-section__heading">
            <h2>One application model. Four concrete steps.</h2>
            <a class="lp-section__anchor" href="how-it-works/">open guide</a>
        </div>
        <p class="lp-section__sub">The point is not to hide infrastructure. The point is to keep the app graph, environment binding, and deploy output in one coherent loop.</p>
    </div>
    <div class="lp-steps">
        <article class="lp-step">
            <div class="lp-step__num">01</div>
            <div class="lp-step__icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <rect x="3" y="3" width="14" height="14" rx="4" class="lp-icon-stroke-accent" stroke-width="1.8"></rect>
                    <path d="M6 10H14M10 6V14" class="lp-icon-stroke-accent" stroke-width="1.8" stroke-linecap="round"></path>
                </svg>
            </div>
            <h3>Declare the primitives</h3>
            <p>Write <code>Store</code>, <code>Table</code>, <code>BlobStore</code>, <code>Topic</code>, and exposed functions in Python instead of hand-wiring cloud resources.</p>
            <span class="lp-step__tag">app code first</span>
        </article>
        <article class="lp-step lp-step--catalog">
            <div class="lp-step__num">02</div>
            <div class="lp-step__icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M4 5.5H16M4 10H16M4 14.5H12" class="lp-icon-stroke-accent" stroke-width="1.8" stroke-linecap="round"></path>
                </svg>
            </div>
            <h3>Bind one environment</h3>
            <p><code>skaal.toml</code> names <code>local</code>, <code>prod</code>, and any other environment you care about. Skaal binds the same app graph against each one.</p>
            <span class="lp-step__tag">skaal.toml</span>
        </article>
        <article class="lp-step lp-step--solve">
            <div class="lp-step__num">03</div>
            <div class="lp-step__icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M4 10L8 14L16 6" class="lp-icon-stroke-highlight" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
                </svg>
            </div>
            <h3>Inspect the bound plan</h3>
            <p>Use <code>skaal plan</code> and <code>skaal map</code> to see what changed and where each resource came from before you render or deploy anything.</p>
            <span class="lp-step__tag">plan + map</span>
        </article>
        <article class="lp-step lp-step--generate">
            <div class="lp-step__num">04</div>
            <div class="lp-step__icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <path d="M5 5H15V15H5V5Z" class="lp-icon-stroke-accent" stroke-width="1.8"></path>
                    <path d="M8 8H12M8 10.5H13M8 13H11" class="lp-icon-stroke-highlight" stroke-width="1.8" stroke-linecap="round"></path>
                </svg>
            </div>
            <h3>Render and own the output</h3>
            <p><code>skaal build</code> and <code>skaal deploy</code> write deploy artifacts you can inspect, keep, and run through Pulumi. Skaal helps generate them. It does not hide them.</p>
            <span class="lp-step__tag">build + deploy</span>
        </article>
    </div>
</section>

<section class="lp-section lp-section--compact" id="environment-loop">
    <div class="lp-section__intro">
        <div class="lp-eyebrow">Environment loop</div>
        <div class="lp-section__heading">
            <h2>The environment file is part of the product.</h2>
            <a class="lp-section__anchor" href="cli-configuration/">configuration</a>
        </div>
        <p class="lp-section__sub">Local development works without configuration. The moment you want named environments, the docs stay concrete: one file for environments, one lock file for pins.</p>
    </div>
    <div class="lp-split">
        <div class="lp-split__col">
            <h3>Define the environment</h3>
            <p>Use <code>skaal.toml</code> to tell Skaal what <code>local</code> and <code>prod</code> mean.</p>
            <pre class="lp-toml"><span class="sec">[env.local]</span>
<span class="key">target</span> = <span class="str">"local"</span>

<span class="sec">[env.prod]</span>
<span class="key">target</span> = <span class="str">"aws"</span>
<span class="key">region</span> = <span class="str">"us-east-1"</span>

<span class="sec">[env.prod.backends.aws]</span>
<span class="key">table_prefix</span> = <span class="str">"prod-"</span></pre>
        </div>
        <div class="lp-split__col">
            <h3>Keep deploy pins explicit</h3>
            <p><code>skaal.lock</code> records concrete bindings per environment, so later plan runs tell you what changed instead of guessing.</p>
            <pre class="lp-toml"><span class="sec">[entries.prod."examples.todo_api.Todos"]</span>
<span class="key">backend</span> = <span class="str">"dynamodb"</span>
<span class="key">region</span> = <span class="str">"us-east-1"</span>

<span class="sec">[entries.prod."examples.todo_api.Comments"]</span>
<span class="key">backend</span> = <span class="str">"postgres"</span>
<span class="key">region</span> = <span class="str">"us-east-1"</span></pre>
        </div>
    </div>
</section>

<section class="lp-section" id="command-surface">
    <div class="lp-section__intro">
        <div class="lp-eyebrow">Command loop</div>
        <div class="lp-section__heading">
            <h2>The CLI reads like the workflow.</h2>
            <a class="lp-section__anchor" href="cli/">CLI</a>
        </div>
        <p class="lp-section__sub">The current alpha keeps the command surface small. That makes the loop easier to evaluate: run locally, inspect the plan, render the artifacts, deploy when you are ready.</p>
    </div>
    <div class="lp-cli">
        <div class="lp-cli__terminal">
            <div class="lp-cli__head">
                <div class="lp-codecard__dots"><i></i><i></i><i></i></div>
                <span class="lp-cli__file">powershell</span>
            </div>
            <pre class="lp-cli__body"><span class="prompt">PS&gt;</span> <span class="cmd">skaal run examples.counter:app --env local</span>
<span class="info">Serving app "counter" on 127.0.0.1:8000</span>

<span class="prompt">PS&gt;</span> <span class="cmd">skaal plan examples.todo_api:app --env prod</span>
<span class="arrow">+</span> <span class="flag">examples.todo_api.Todos</span> <span class="arg">store</span> <span class="ok">dynamodb</span>
<span class="arrow">+</span> <span class="flag">examples.todo_api.Comments</span> <span class="arg">table</span> <span class="ok">postgres</span>

<span class="prompt">PS&gt;</span> <span class="cmd">skaal build examples.todo_api:app --env prod</span>
<span class="info">Built 4 resource artifact(s) -&gt; .skaal/build/prod</span>

<span class="prompt">PS&gt;</span> <span class="cmd">skaal deploy examples.todo_api:app --env prod --preview</span>
<span class="info">Pulumi stack todos-prod</span></pre>
        </div>
        <div class="lp-cli__commands">
            <div class="lp-cmd">
                <span class="lp-cmd__name">run</span>
                <div class="lp-cmd__desc"><b>Local runtime.</b> Bind one environment and serve the app as it exists now.</div>
            </div>
            <div class="lp-cmd">
                <span class="lp-cmd__name">plan</span>
                <div class="lp-cmd__desc"><b>Diff the bound plan.</b> See what changed before touching deploy output.</div>
            </div>
            <div class="lp-cmd">
                <span class="lp-cmd__name">map</span>
                <div class="lp-cmd__desc"><b>Trace the graph.</b> Print the source-to-resource tree and emit JSON for machines.</div>
            </div>
            <div class="lp-cmd">
                <span class="lp-cmd__name">build</span>
                <div class="lp-cmd__desc"><b>Render artifacts.</b> Write Dockerfiles, entrypoints, and Pulumi files without deploying.</div>
            </div>
            <div class="lp-cmd">
                <span class="lp-cmd__name">deploy</span>
                <div class="lp-cmd__desc"><b>Apply with Pulumi.</b> Render again, preview or apply, then update <code>skaal.lock</code>.</div>
            </div>
        </div>
    </div>
</section>

<section class="lp-section" id="what-you-can-ship">
    <div class="lp-section__intro">
        <div class="lp-eyebrow">What you can ship</div>
        <div class="lp-section__heading">
            <h2>Build the service shapes you already recognize.</h2>
            <a class="lp-section__anchor" href="examples/">examples</a>
        </div>
        <p class="lp-section__sub">Skaal is not trying to invent a new category of app. It is trying to make the infrastructure declaration live inside the Python service you were already going to write.</p>
    </div>
    <div class="lp-uses">
        <article class="lp-use">
            <p class="lp-use__lead">Mounted HTTP API</p>
            <h3>FastAPI or Starlette on top, Skaal behind it</h3>
            <ul>
                <li>use public routes, auth, validation, and OpenAPI from your web framework</li>
                <li>keep <code>Store</code>, <code>Table</code>, and exposed functions in the same app graph</li>
                <li>start from <a href="tutorials/http-api/">Tutorial 2</a> or <a href="examples/">Todo API</a></li>
            </ul>
        </article>
        <article class="lp-use">
            <p class="lp-use__lead">Data-backed service</p>
            <h3>Key-value, relational, blob, and topic surfaces together</h3>
            <ul>
                <li>mix <code>Store</code>, <code>Table</code>, and <code>BlobStore</code> without splitting the deploy story</li>
                <li>bind local and cloud environments from the same declarations</li>
                <li>inspect the result through <a href="how-it-works/">How it works</a> and <a href="concepts/">Concepts</a></li>
            </ul>
        </article>
        <article class="lp-use">
            <p class="lp-use__lead">Streaming and jobs</p>
            <h3>Async responses, scheduled work, and typed events</h3>
            <ul>
                <li>stream responses with <code>app.invoke_stream(...)</code></li>
                <li>publish to topics and schedule recurring work next to the business logic</li>
                <li>use <a href="tutorials/files-and-streaming/">Tutorial 5</a> and the repo examples as anchors</li>
            </ul>
        </article>
    </div>
</section>

<section class="lp-cta">
    <div class="lp-cta__inner">
        <div>
            <h2>Decide in one afternoon.</h2>
            <p class="lp-cta__lead">Read the concepts, run the counter app, inspect the environment loop, and decide whether code-first infrastructure is the right trade for your team.</p>
            <div class="lp-cta__actions">
                <a class="sk-btn sk-btn--primary" href="getting-started/">Start with the local loop</a>
                <a class="sk-btn sk-btn--ghost" href="tutorials/">Walk the tutorials</a>
            </div>
        </div>
        <div class="lp-cta__links">
            <h4>Read next</h4>
            <ul>
                <li><a href="concepts/">Concepts</a> <span>glossary of the model</span></li>
                <li><a href="how-it-works/">How it works</a> <span>declare -&gt; infer -&gt; bind -&gt; deploy</span></li>
                <li><a href="comparison/">Comparison</a> <span>when plain Pulumi or a platform is simpler</span></li>
                <li><a href="whats-new/">What's new</a> <span>current alpha scope and gaps</span></li>
            </ul>
        </div>
    </div>
</section>
