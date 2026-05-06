---
hide:
  - navigation
  - toc
---
<section class="lp-hero" id="top">
  <div class="lp-hero__copy">
    <span class="lp-kicker"><span class="lp-kicker__pulse"></span>Infrastructure as Constraints for Python</span>
    <h1 class="lp-hero__h1">Stop hard-coding the backend.<br /><em>Declare the contract instead.</em></h1>
    <p class="lp-hero__lead">
      You picked SQLite to start, then rewrote the data layer for Postgres, then again for DynamoDB.
      Each migration leaked infra into business code. Skaal lets you declare the <em>behavior</em>
      a resource needs &mdash; latency, durability, throughput, residency &mdash; and a Z3 solver picks
      the cheapest backend in your catalog that satisfies it. Local, AWS, and GCP, from one app file.
    </p>
    <div class="lp-hero__actions">
      <a class="sk-btn sk-btn--primary" href="tutorials/">Start tutorials</a>
      <a class="sk-btn sk-btn--ghost" href="cli/">Browse the CLI</a>
      <span class="sk-btn sk-btn--ghost sk-btn--copy"><code>pip install &quot;skaal[serve]&quot;</code></span>
    </div>
    <div class="lp-hero__meta">
      <span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
        One app model, many targets
      </span>
      <span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
        Auditable plan.skaal.lock output
      </span>
      <span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L20 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" /></svg>
        Local, AWS, and GCP
      </span>
    </div>
  </div>

  <div class="lp-hero__visual">
    <div class="lp-codecard">
      <div class="lp-codecard__head">
        <div class="lp-codecard__dots"><i></i><i></i><i></i></div>
        <span class="lp-codecard__file">app.py</span>
        <span class="lp-codecard__lang">Python</span>
      </div>
      <pre class="lp-codecard__body"><span class="kw">from</span> skaal <span class="kw">import</span> App, storage
<span class="kw">from</span> skaal.storage <span class="kw">import</span> Map

app = <span class="cls">App</span>(<span class="str">&quot;todo&quot;</span>)


<span class="deco">@storage</span>(
    read_latency=<span class="str">&quot;&lt; 10ms&quot;</span>,
    durability=<span class="str">&quot;strong&quot;</span>,
    throughput=<span class="str">&quot;&gt; 100 rps&quot;</span>,
    retention=<span class="str">&quot;30d&quot;</span>,
)
<span class="kw">class</span> <span class="cls">Todos</span>(<span class="cls">Map</span>[<span class="cls">str</span>, <span class="cls">dict</span>]):
    <span class="kw">pass</span></pre>
    </div>

    <div class="lp-flowarrow" aria-hidden="true">
      <span class="lp-flowarrow__line"></span>
      <span class="lp-flowarrow__dot"></span>
      Solve
      <span class="lp-flowarrow__dot"></span>
      <span class="lp-flowarrow__line"></span>
    </div>

    <div class="lp-plancard">
      <div class="lp-plancard__head">
        <h4>plan.skaal.lock - target=aws</h4>
        <span class="sk-sig sk-sig--resolved"><span class="sk-sig__dot"></span>Resolved</span>
      </div>
      <div class="lp-plancard__body">
        <div class="lp-plancard__title-row">
          <h4>Storage.Todos</h4>
          <span>3 candidates evaluated</span>
        </div>
        <div class="lp-bcand is-selected">
          <span class="lp-bcand__name">dynamodb</span>
          <span class="lp-bcand__cost">$0.018 / wu - 7ms p50</span>
          <span class="lp-bcand__tag">selected</span>
        </div>
        <div class="lp-bcand is-rejected">
          <span class="lp-bcand__name">postgres</span>
          <span class="lp-bcand__cost">$0.024 / wu - 12ms p50</span>
          <span class="lp-bcand__tag">cost</span>
        </div>
        <div class="lp-bcand is-rejected">
          <span class="lp-bcand__name">sqlite</span>
          <span class="lp-bcand__cost">$0 - 5ms p50</span>
          <span class="lp-bcand__tag">throughput</span>
        </div>
      </div>
    </div>
  </div>
</section>

<div class="lp-installstrip">
  <span class="lp-installstrip__lbl">Runs on</span>
  <div class="lp-installstrip__items">
    <span><code>Python 3.11+</code></span>
    <span>Z3 solver</span>
    <span>SQLite, Postgres, Redis</span>
    <span>DynamoDB, Firestore</span>
    <span>S3, GCS, Local FS</span>
    <span>Pulumi, Docker, Lambda, Cloud Run</span>
  </div>
</div>

<nav class="lp-quicknav" aria-label="Jump to homepage sections">
  <a class="lp-quicknav__link" href="#how">How it works</a>
  <a class="lp-quicknav__link" href="#use-cases">Use cases</a>
  <a class="lp-quicknav__link" href="#tiers">Storage tiers</a>
  <a class="lp-quicknav__link" href="#catalogs">Catalogs</a>
  <a class="lp-quicknav__link" href="#cli">CLI loop</a>
  <a class="lp-quicknav__link" href="#compare">Compare &amp; FAQ</a>
  <a class="lp-quicknav__link" href="#tutorials">Tutorials</a>
</nav>

<section class="lp-section" id="how">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">How Skaal works</span>
    <div class="lp-section__heading">
      <h2>Stop hard-coding the stack into your business logic.</h2>
      <a class="lp-section__anchor" href="#how" aria-label="Link to how-it-works section">#how</a>
    </div>
    <p class="lp-section__sub">
      Most frameworks make you choose infrastructure on day one. Skaal flips that trade:
      describe the behavior your code needs, solve it against a catalog, and keep the
      application model stable while the target changes underneath it.
    </p>
  </div>

  <div class="lp-steps">
    <div class="lp-step lp-step--declare">
      <div class="lp-step__icon">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><path d="M5 9h12M22 9h5M5 16h5M15 16h12M5 23h17" stroke="currentColor" stroke-width="2" stroke-linecap="round" /><circle class="lp-icon-fill-accent" cx="19" cy="9" r="3" /><circle class="lp-icon-fill-highlight" cx="12" cy="16" r="3" /><circle class="lp-icon-fill-accent" cx="24" cy="23" r="3" /></svg>
      </div>
      <span class="lp-step__num">01 / Declare</span>
      <h3>Constraints, not connection strings</h3>
      <p>Express latency, durability, throughput, residency, and access patterns on typed surfaces like <code>Map</code>, <code>Collection</code>, <code>BlobStore</code>, and <code>VectorStore</code>.</p>
      <span class="lp-step__tag">@storage, @function, @schedule</span>
    </div>
    <div class="lp-step lp-step--catalog">
      <div class="lp-step__icon">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><rect x="4" y="6" width="10" height="6" rx="1.5" stroke="currentColor" stroke-width="2" /><rect x="18" y="6" width="10" height="6" rx="1.5" stroke="currentColor" stroke-width="2" /><rect x="4" y="20" width="10" height="6" rx="1.5" stroke="currentColor" stroke-width="2" /><rect x="18" y="20" width="10" height="6" rx="1.5" stroke="currentColor" stroke-width="2" /><path class="lp-icon-stroke-accent" d="M9 12v8M23 12v8" stroke-width="2" /></svg>
      </div>
      <span class="lp-step__num">02 / Catalog</span>
      <h3>Describe what each environment can do</h3>
      <p>Per-environment TOML catalogs list real backend options, costs, and capability flags. Use overlay catalogs to move from dev to prod without forking the app.</p>
      <span class="lp-step__tag">catalogs/local.toml, aws.toml</span>
    </div>
    <div class="lp-step lp-step--solve">
      <div class="lp-step__icon">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><circle cx="8" cy="9" r="3" stroke="currentColor" stroke-width="2" /><circle cx="24" cy="9" r="3" stroke="currentColor" stroke-width="2" /><circle class="lp-icon-fill-highlight" cx="16" cy="23" r="3" /><path class="lp-icon-stroke-accent" d="M10 11l5 9M22 11l-5 9" stroke-width="2" /></svg>
      </div>
      <span class="lp-step__num">03 / Solve</span>
      <h3>The Z3 planner picks the cheapest valid path</h3>
      <p>Each declared need becomes part of the solve. The result is an explicit plan file with selected and rejected candidates instead of hidden framework defaults.</p>
      <span class="lp-step__tag">plan.skaal.lock, skaal plan --explain</span>
    </div>
    <div class="lp-step lp-step--generate">
      <div class="lp-step__icon">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><path d="M9 4h10l5 5v17a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="2" /><path d="M19 4v5h5" stroke="currentColor" stroke-width="2" /><path class="lp-icon-stroke-accent" d="M12 16h8M12 21h6" stroke-width="2" stroke-linecap="round" /></svg>
      </div>
      <span class="lp-step__num">04 / Generate</span>
      <h3>Artifacts and runtime surfaces, ready to ship</h3>
      <p>Skaal emits the runtime entry point, Dockerfile, Pulumi program, and stack metadata under <code>artifacts/</code>, then deploy hands off to Pulumi.</p>
      <span class="lp-step__tag">artifacts/, Lambda, Cloud Run, Docker</span>
    </div>
  </div>
</section>

<section class="lp-section" id="use-cases">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Built for</span>
    <div class="lp-section__heading">
      <h2>The application shapes Skaal is meant to support.</h2>
      <a class="lp-section__anchor" href="#use-cases" aria-label="Link to use-cases section">#use-cases</a>
    </div>
    <p class="lp-section__sub">
      Real services, not toy CRUD. Mount FastAPI, Starlette, Dash, or another ASGI or WSGI
      framework and let Skaal handle the storage, scheduling, and deployment scaffolding.
    </p>
  </div>

  <div class="lp-uses">
    <div class="lp-use">
      <p class="lp-use__lead">Backends</p>
      <h3>API + Postgres + queue</h3>
      <ul>
        <li>FastAPI mounted via <code>mount_asgi</code></li>
        <li>SQLModel entities with Alembic migrations</li>
        <li>Outbox-backed background jobs</li>
        <li>Per-route retry and rate-limit policies</li>
      </ul>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">RAG and AI</p>
      <h3>Vector retrieval at scale</h3>
      <ul>
        <li><code>VectorStore</code> with metadata filters</li>
        <li>Embeddings declared on the surface</li>
        <li><code>BlobStore</code> for source documents</li>
        <li>Streamed responses via mounted ASGI</li>
      </ul>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Internal tools</p>
      <h3>Dash app + scheduled ETL</h3>
      <ul>
        <li>Dash mounted via <code>mount_wsgi</code></li>
        <li><code>@app.schedule</code> cron jobs</li>
        <li>Relational tier as the data layer</li>
        <li>Local dev to Cloud Run with one catalog swap</li>
      </ul>
    </div>
  </div>
</section>

<section class="lp-section" id="tiers">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Storage surfaces</span>
    <div class="lp-section__heading">
      <h2>Six tiers. One declarative API.</h2>
      <a class="lp-section__anchor" href="#tiers" aria-label="Link to storage tiers section">#tiers</a>
    </div>
    <p class="lp-section__sub">
      Skaal ships first-class surfaces for the storage shapes real applications reach for.
      Backend choice happens at solve time, so your code keeps the same API from local dev
      to production.
    </p>
  </div>

  <div class="lp-tiers">
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Key-value</h3>
        <span class="lp-tier__deco">Map, Collection</span>
      </div>
      <p>Generic stores with cursor pagination, secondary indexes, and per-row TTL via <code>retention=</code>.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">SQLite</span>
        <span class="lp-tier__be">Postgres</span>
        <span class="lp-tier__be">Redis</span>
        <span class="lp-tier__be">DynamoDB</span>
        <span class="lp-tier__be">Firestore</span>
      </div>
    </div>
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Relational</h3>
        <span class="lp-tier__deco">@app.relational</span>
      </div>
      <p>SQLModel-backed entities with Alembic migrations, autogenerate, upgrade, downgrade, drift checks, and dry-run SQL.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">SQLite</span>
        <span class="lp-tier__be">Postgres</span>
        <span class="lp-tier__be is-new">Alembic</span>
      </div>
    </div>
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Vector</h3>
        <span class="lp-tier__deco">VectorStore</span>
      </div>
      <p>Similarity search with metadata filters, namespaces, and embedding configuration attached to the surface.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">Chroma</span>
        <span class="lp-tier__be">pgvector</span>
        <span class="lp-tier__be">Pinecone</span>
      </div>
    </div>
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Blob</h3>
        <span class="lp-tier__deco">BlobStore</span>
      </div>
      <p>Object storage with streamed uploads, presigned URLs, metadata, and the same constraint vocabulary as the rest of the platform.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">Local FS</span>
        <span class="lp-tier__be is-new">S3</span>
        <span class="lp-tier__be is-new">GCS</span>
      </div>
    </div>
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Channels</h3>
        <span class="lp-tier__deco">EventLog, Outbox</span>
      </div>
      <p>Durable event streams with replay-by-offset, consumer groups, and Outbox-backed at-least-once relay.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">Local KV</span>
        <span class="lp-tier__be">Redis Streams</span>
        <span class="lp-tier__be">SNS, SQS</span>
      </div>
    </div>
    <div class="lp-tier">
      <div class="lp-tier__head">
        <h3>Compute</h3>
        <span class="lp-tier__deco">@app.function, @app.job</span>
      </div>
      <p>Functions, schedules, and background work with retries, circuit breakers, rate limits, and bulkheads attached per function.</p>
      <div class="lp-tier__backends">
        <span class="lp-tier__be">Local async</span>
        <span class="lp-tier__be">Lambda</span>
        <span class="lp-tier__be">Cloud Run</span>
      </div>
    </div>
  </div>
</section>

<section class="lp-section" id="catalogs">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Catalog overlays</span>
    <div class="lp-section__heading">
      <h2>One app. Many environments. Zero forks.</h2>
      <a class="lp-section__anchor" href="#catalogs" aria-label="Link to catalogs section">#catalogs</a>
    </div>
    <p class="lp-section__sub">
      Catalogs inherit and override. Stage a higher-durability production stack on top of
      your development catalog with <code>extends</code>, and keep the source of every
      backend explicit in the merged result.
    </p>
  </div>

  <div class="lp-split">
    <div class="lp-split__col">
      <h3>catalogs/local.toml</h3>
      <p>Development defaults for fast feedback and low ceremony.</p>
      <pre class="lp-toml"><span class="cmt"># base catalog</span>
<span class="sec">[storage.sqlite]</span>
<span class="key">read_latency</span>  = <span class="str">"&lt; 5ms"</span>
<span class="key">durability</span>    = <span class="str">"local"</span>
<span class="key">throughput</span>    = <span class="str">"&gt; 5000 rps"</span>
<span class="key">cost_per_unit</span> = <span class="num">0.0</span>
<span class="key">supports_ttl</span>  = true

<span class="sec">[storage.redis]</span>
<span class="key">read_latency</span>  = <span class="str">"&lt; 2ms"</span>
<span class="key">durability</span>    = <span class="str">"ephemeral"</span></pre>
    </div>
    <div class="lp-split__col">
      <h3>catalogs/prod.toml</h3>
      <p>Overlay the base catalog and swap in managed services.</p>
      <pre class="lp-toml"><span class="sec">[skaal]</span>
<span class="key">extends</span> = <span class="str">"./local.toml"</span>
<span class="key">remove</span>  = [<span class="str">"storage.sqlite"</span>]

<span class="sec">[storage.dynamodb]</span>
<span class="key">read_latency</span>  = <span class="str">"&lt; 8ms"</span>
<span class="key">durability</span>    = <span class="str">"strong"</span>
<span class="key">throughput</span>    = <span class="str">"&gt; 10000 rps"</span>
<span class="key">residency</span>     = <span class="str">"eu-west-1"</span>
<span class="key">cost_per_unit</span> = <span class="num">0.018</span>

<span class="sec">[storage.dynamodb.deploy]</span>
<span class="key">table_class</span>   = <span class="str">"STANDARD_IA"</span>
<span class="key">billing_mode</span>  = <span class="str">"PAY_PER_REQUEST"</span></pre>
    </div>
  </div>
</section>

<section class="lp-section" id="cli">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Command line</span>
    <div class="lp-section__heading">
      <h2>From install to deploy in the same planner-shaped loop.</h2>
      <a class="lp-section__anchor" href="#cli" aria-label="Link to CLI section">#cli</a>
    </div>
    <p class="lp-section__sub">
      The CLI is organized around the plan file. Every command works from the same resolved
      state, so the runtime and deployment artifacts stay regenerable and auditable.
    </p>
  </div>

  <div class="lp-cli">
    <div class="lp-cli__terminal">
      <div class="lp-cli__head">
        <div class="lp-codecard__dots"><i></i><i></i><i></i></div>
        <span class="lp-cli__file">~/projects/todo</span>
      </div>
      <pre class="lp-cli__body"><span class="prompt">$</span> <span class="cmd">pip install</span> <span class="arg">&quot;skaal[serve,runtime]&quot;</span>
<span class="prompt">$</span> <span class="cmd">skaal init</span> <span class="arg">todo</span> <span class="cmt"># scaffolds ./todo/</span>
<span class="prompt">$</span> <span class="cmd">skaal run</span> <span class="flag">--reload</span>
<span class="info">&gt; watching ./ for changes</span>
<span class="info">&gt; using catalog: catalogs/local.toml</span>
<span class="info">&gt; solve: 3 candidates -&gt; sqlite (selected)</span>
<span class="ok">ok http://127.0.0.1:8000 - ready in 412ms</span>

<span class="prompt">$</span> <span class="cmd">skaal plan</span> <span class="flag">--catalog</span> <span class="arg">catalogs/prod.toml</span>
<span class="info">  Storage.Todos       </span><span class="arrow">-&gt;</span><span class="info"> dynamodb    7ms p50  $0.018/wu</span>
<span class="info">  Storage.Sessions    </span><span class="arrow">-&gt;</span><span class="info"> redis       1ms p50  $0.004/wu</span>
<span class="info">  Compute.create_todo </span><span class="arrow">-&gt;</span><span class="info"> lambda      cold 280ms</span>
<span class="ok">ok resolved - plan.skaal.lock written</span></pre>
    </div>

    <div class="lp-cli__commands">
      <div class="lp-cmd">
        <span class="lp-cmd__name">skaal init</span>
        <span class="lp-cmd__desc"><b>Scaffold</b> a starter project with a base catalog, a hello-world app, and a deployable layout.</span>
      </div>
      <div class="lp-cmd">
        <span class="lp-cmd__name">skaal run</span>
        <span class="lp-cmd__desc"><b>Local dev loop</b> with auto-reload, mounted ASGI or WSGI apps, and runtime engines started for you.</span>
      </div>
      <div class="lp-cmd">
        <span class="lp-cmd__name">skaal plan</span>
        <span class="lp-cmd__desc"><b>Solve</b> the catalog against your constraints and write <code>plan.skaal.lock</code> with reasons and rejected candidates.</span>
      </div>
      <div class="lp-cmd">
        <span class="lp-cmd__name">skaal build</span>
        <span class="lp-cmd__desc"><b>Generate</b> the runtime entry point, Dockerfile, and Pulumi program for the resolved plan.</span>
      </div>
      <div class="lp-cmd">
        <span class="lp-cmd__name">skaal deploy</span>
        <span class="lp-cmd__desc"><b>Ship</b> the generated target artifacts without hand-maintaining deployment glue.</span>
      </div>
    </div>
  </div>
</section>

<section class="lp-section lp-section--compact" id="compare">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Compare &amp; FAQ</span>
    <div class="lp-section__heading">
      <h2>Where Skaal sits, and the questions you'd ask before adopting it.</h2>
      <a class="lp-section__anchor" href="#compare" aria-label="Link to compare and FAQ section">#compare</a>
    </div>
    <p class="lp-section__sub">
      Skaal isn't trying to be Encore, SST, Wing, Modal, or plain Pulumi &mdash; it overlaps
      with each in a different way. The comparison page maps the differences honestly,
      and the FAQ covers lock-in, license, and the eject path.
    </p>
  </div>

  <div class="lp-uses">
    <div class="lp-use">
      <p class="lp-use__lead">Compare</p>
      <h3>Skaal vs. the alternatives</h3>
      <p>Side-by-side with Encore, SST, Wing, Modal, and Pulumi. Includes &ldquo;when another tool wins&rdquo; for each.</p>
      <p><a href="comparison/">Read the comparison</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">FAQ</p>
      <h3>Lock-in, license, and ejection</h3>
      <p>Can you keep the generated Pulumi if you stop using Skaal? Is GPL-3.0 compatible with a closed SaaS? What does the solver do when constraints are unsatisfiable?</p>
      <p><a href="faq/">Read the FAQ</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Not for you if</p>
      <h3>Honest disqualifiers</h3>
      <ul>
        <li>You already maintain a mature Terraform / CDK monorepo.</li>
        <li>Your stack relies on backends Skaal doesn't model (Kafka, Spanner, Cosmos DB).</li>
        <li>You can't take a GPL-3.0-or-later runtime dependency.</li>
        <li>You need production-grade GCP today.</li>
      </ul>
    </div>
  </div>
</section>

<section class="lp-section" id="tutorials">
  <div class="lp-section__intro">
    <span class="lp-eyebrow">Tutorial path</span>
    <div class="lp-section__heading">
      <h2>Learn Skaal in five progressive passes.</h2>
      <a class="lp-section__anchor" href="#tutorials" aria-label="Link to tutorials section">#tutorials</a>
    </div>
    <p class="lp-section__sub">
      The tutorials are written against real code in this repository and add one concept at a time:
      local storage first, mounted HTTP next, then planning, deployment, migrations, uploads, and streams.
    </p>
  </div>

  <div class="lp-uses">
    <div class="lp-use">
      <p class="lp-use__lead">Tutorial 1</p>
      <h3>Build a counter app</h3>
      <p>Start with <code>App</code>, <code>Store</code>, <code>@app.storage</code>, and <code>@app.function</code>, then run the generated HTTP surface locally.</p>
      <p><a href="tutorials/first-app/">Start tutorial</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Tutorial 2</p>
      <h3>Mount FastAPI</h3>
      <p>Keep your public routes in FastAPI and route application work through Skaal compute with <code>app.invoke(...)</code>.</p>
      <p><a href="tutorials/http-api/">Start tutorial</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Tutorial 3</p>
      <h3>Solve, build, deploy</h3>
      <p>Inspect catalogs, write <code>plan.skaal.lock</code>, generate artifacts, and move the same app model to a new target.</p>
      <p><a href="tutorials/planning-and-deployment/">Start tutorial</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Tutorial 4</p>
      <h3>Add relational data</h3>
      <p>Introduce SQLModel-backed storage and use the relational migration commands instead of hand-maintaining schema changes.</p>
      <p><a href="tutorials/relational-and-migrations/">Start tutorial</a></p>
    </div>
    <div class="lp-use">
      <p class="lp-use__lead">Tutorial 5</p>
      <h3>Handle files and streams</h3>
      <p>Finish with blob uploads, pagination-friendly file listing, and streaming responses from Skaal functions.</p>
      <p><a href="tutorials/files-and-streaming/">Start tutorial</a></p>
    </div>
  </div>
</section>

<section class="lp-cta">
  <div class="lp-cta__inner">
    <div>
      <h2>Stop writing the same plumbing for every new app.</h2>
      <p class="lp-cta__lead">
        Declare the contract once. Let Skaal pick the stack, generate the artifacts, and
        keep your code portable from your laptop to the next environment you need to ship.
      </p>
      <div class="lp-cta__actions">
        <a class="sk-btn sk-btn--primary" href="getting-started/">Read the quickstart</a>
        <a class="sk-btn sk-btn--ghost" href="https://github.com/Elouen-ginat/Skaal" target="_blank" rel="noreferrer">Star on GitHub</a>
      </div>
    </div>
    <div class="lp-cta__links">
      <h4>Read next</h4>
      <ul>
        <li><a href="how-it-works/">How Skaal Works</a><span>Planner lifecycle</span></li>
        <li><a href="comparison/">Comparison</a><span>Skaal vs. Encore, SST, Wing, Modal, Pulumi</span></li>
        <li><a href="faq/">FAQ</a><span>Lock-in, license, eject path</span></li>
        <li><a href="platform-features/">Platform Features</a><span>Surfaces and runtime</span></li>
        <li><a href="catalogs/">Catalogs</a><span>Overlay model</span></li>
        <li><a href="reference/python-api/">Python API</a><span>In-process orchestration</span></li>
      </ul>
    </div>
  </div>
</section>
