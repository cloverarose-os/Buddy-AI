# Buddy AI - Future Roadmap

Planned capabilities, grouped by the underlying mechanism they use (not by how
they feel to the user). Features in the same group share infrastructure; features
in different groups are independent tracks that can be built in parallel.

This is a planning document - nothing here is built yet. It exists so the plan
isn't forgotten, and so each feature is designed against the right mechanism.

## The core insight: four groups, four mechanisms

1. **Tool-loop features** - the model decides to call a capability mid-answer.
   Plug into the brain's EXISTING tool-calling loop (same path image generation
   already uses). Web search, terminal, filesystem.
2. **Retrieval backbone (vector/embeddings RAG)** - store a corpus, retrieve the
   relevant chunks into context at answer time. ONE backbone serves three
   features: personal memory, private documents, oversized reference material.
3. **Vision** - its own path; partly scaffolded already (`describe_image` +
   `gemma3:12b` are in the brain today). Webcam or file-picker as the input.
4. **Coding ability** - comes from the MODEL, not from RAG or fine-tuning. A
   specialized coding model is the real lever.

These do NOT all collapse into one system. Designing memory well does not give
web search for free, and coding ability can't be bolted on with retrieval.

## Group 1: Tool-loop features

The brain already has a native tool-calling loop (it's how the model decides to
generate an image). These features add new tools to that same loop.

### Web search / current events
- **Goal:** answer about things after the model's training cutoff - today's news,
  a political event, current weather.
- **Mechanism:** a `web_search` tool the model can call. On call, hit a search
  API, pull back result text, hand it to the model to answer from. This is
  "retrieval then generation" loosely, but it is NOT the vector/embeddings kind
  of RAG - the retrieval source is the live web, via an API call.
- **Effort:** relatively low - it slots into the existing tool loop. Mostly
  "define the tool + pick a search provider."
- **Provider decision:** the user wants the BEST FREE option. Findings:
  - **Brave Search API (recommended):** genuine free tier (~2,000 queries/mo),
    a real independent index, clean structured results, needs a free API key.
    Best free general-search quality.
  - **Tavily:** purpose-built for LLMs (returns pre-summarized, LLM-ready
    results), free tier ~1,000 queries/mo, needs a key. Easiest to wire in;
    close second.
  - **DuckDuckGo:** no key at all, truly free, but its instant-answer API is
    weaker for broad "what happened today" current-events queries.
  - Verify current free-tier limits before building (they change).

#### KNOWN LIMITATION: local model paraphrases, it does not vet
- **What web search actually does with a small (9B) model:** it feeds the model
  the top search-result snippets, and the model PARAPHRASES them into a fluent
  reply. It does NOT read full articles, cross-check sources, weigh credibility,
  or build an independent picture of an event. For "what's the weather" this is
  fine (no judgment needed). For "is it true that X did an awful thing yesterday"
  it is NOT reliable - the answer inherits whatever the top snippets say, stated
  with more confidence than warranted.
- **Root cause is MODEL SIZE, not the search plumbing.** Critical synthesis -
  distinguishing reported/alleged from confirmed, noticing when sources disagree,
  judging trustworthiness - is a reasoning capability that scales with model
  size. Feeding fuller article text helps a small model paraphrase more
  ACCURATELY, but does not give it the JUDGMENT to vet. That ceiling is inherent
  to a local 9B.
- **Possible future consideration (NOT a committed plan):** the same kind of
  "elevate to a frontier model" mechanism discussed for coding could also serve
  "critically vet this news/claim." Same web_search tool underneath; a bigger
  model does the reasoning over the results.
- **User's stance (important):** the user is hesitant to open more doors to an
  outside company's model, and this is NOT being pursued now. Recorded only as a
  limitation to be aware of and a possibility to revisit, not a direction chosen.
  In the meantime, treat Buddy's web answers as "here's what the top results say,"
  not "here's the vetted truth."

### Terminal access
- **Goal:** let Buddy run commands on the machine.
- **Mechanism:** a tool that executes a shell command and returns output.
- **RISK - highest of any feature here.** A model with a shell can delete or
  break things if it misfires. MUST have guardrails: confirmation before
  execution, an allow/deny policy, and probably a dry-run/preview. Do NOT build
  this as "model runs whatever it wants."

### Filesystem access
- **Goal:** let Buddy read/edit files on the machine.
- **Mechanism:** tools for read/list/edit scoped to allowed directories.
- **RISK - high, same family as terminal.** Scope to specific folders; never
  hand it the whole drive unsupervised. Read-only first is much safer than
  read-write.

**Note on trust (user's own framing):** the coding + terminal + filesystem combo
is only wanted "if the coding is trustworthy enough." That's the right instinct -
these three together are what turns Buddy from a companion into something that can
act on the system, and that power cuts both ways. Build them behind confirmation
gates and start read-only / preview-only.

## Group 2: The retrieval backbone (vector / embeddings RAG)

ONE piece of infrastructure serves three features. Build it once, deliberately,
because three things depend on it. You already have `nomic-embed-text` installed
(the embedding model), so the pieces are on the machine.

**How it works (plain version):** text is turned into "embeddings" (numeric
fingerprints of meaning) and stored. On a new prompt, the prompt is embedded too,
and the store returns the few most *semantically relevant* chunks, which get
injected into context. This is what lets memory scale WITHOUT stuffing everything
into every prompt - only the relevant bits are pulled each time. That directly
answers the user's speed concern: it does NOT re-read all memory every turn; it
retrieves a small relevant slice.

### 2a. Personal long-term memory
- **Goal:** Buddy recalls durable facts later when relevant ("my dog is Luna").
  This is DISTINCT from the 16-message conversation window, which is just
  short-term context and is fine as-is.
- **Design decisions still open:**
  - *Storing:* explicit ("Buddy, remember X"), automatic (model extracts facts
    worth keeping), or both.
  - *Editability:* a human-readable store the user can open and edit is nice.
  - *Scale:* personal facts grow slowly; the vector approach handles growth
    gracefully.
- **Persistence note:** lives in `shared/` on the machine (off GitHub), survives
  restarts, lost on a fresh install - which matches the user's stated
  expectation exactly.

### 2b. Private documents
- **Goal:** ask Buddy about your own files/notes.
- **Mechanism:** same backbone - embed the documents, retrieve relevant chunks.
- Adds a step: ingesting/chunking documents into the store.

### 2c. Oversized reference material
- **Goal:** reference manuals / knowledge bases too big to fit in context.
- **Mechanism:** same backbone; just a larger corpus.

**Shared build:** an embedding step, a vector store, and a retrieval step wired
into the brain before it answers. 2a/2b/2c differ mainly in what goes IN and how
it's chunked, not in the core machinery.

## Group 3: Vision

Its own path - does not touch the tool loop or the retrieval backbone. Notably,
this is PARTLY BUILT already: the brain has a `describe_image` routing function
and `gemma3:12b` (the vision model) is installed and used when an image is
attached today.

### Goal
Buddy can "see" - process an image as context for a prompt. Two input methods:
- **File picker:** a button in the "talk to Buddy" box that opens the file
  explorer; the chosen file is attached as context for the next prompt/question.
- **Webcam:** capture a frame from the webcam as the image context.

### Mechanism
- The brain vision path largely exists. The main new work is COMPANION-SIDE UI:
  the attach button, the file dialog, sending the image bytes to the brain, and
  (for webcam) grabbing a frame.
- Vision model already selected (`gemma3:12b`).

### The file-picker interaction + animation (user's design)
A charming bit of interaction design, worth capturing verbatim:
- Click the attach button -> Buddy extends his hand, waiting to take something.
- On selecting a file -> he holds it a second with a THUMBNAIL of the file shown
  on his hand.
- Then he reaches behind his back as if pocketing it, and returns to idle -
  signaling "I've got your file, now give me your prompt + hit send."

**Build split:**
- *Function:* attach button -> file dialog -> send image to the brain's existing
  vision path. Straightforward.
- *Animation:* a custom emote sequence in the renderer (hand-extend -> hold ->
  reach-behind -> idle). The one genuinely new rendering piece is compositing the
  real file's thumbnail onto the paw for a beat. Fits the existing emote system.

## Group 4: Coding ability

The hardest to make "genuinely useful" (the user's explicit bar). Coding skill
comes from the MODEL - RAG and fine-tuning cannot manufacture it. RAG can only
GROUND a capable model in your own codebase; fine-tuning is expensive, slow, and
won't match a purpose-built coder, so it's off the table.

### DECISION (reached): Gemini free-tier API, human fallback to the app

The chosen approach routes coding OFF-SITE to a frontier model rather than
running a local coding model. The user accepted letting the self-hosted principle
go for THIS ONE category, in exchange for frontier-quality coding.

- **Built-in coding channel:** route "coding mode" requests to the **Gemini free
  tier** (a real free API tier; usable for personal volume). Cost: **$0 extra.**
- **Fallback:** when the built-in result isn't good enough, the USER manually
  takes the problem to their existing **$20/month Claude/Gemini app subscription**
  (money already spent). This fallback is a HUMAN workflow, not code - Buddy does
  not auto-escalate. So there is no metered API that can surprise-bill.
- **Net monthly cost of the feature: $0** beyond the subscription already paid.

### Why not the other paths (recorded so it isn't re-litigated)

- **Local specialized coding model** (Qwen-Coder / DeepSeek-Coder via Ollama):
  fully self-hosted and free per use, but quality is capped by what a ~7-14B
  model on a 12 GB card can do, and it competes for VRAM. Viable, but the user
  preferred frontier quality for this one category.
- **Paid frontier API with a hard cap** (e.g. Claude API, prepaid/capped):
  surprise-proof via a hard cap, does NOT train on your data, frontier quality -
  BUT it is a SEPARATE meter from the $20 app subscription, so it costs MORE than
  $20 total. The user's line was "not one dollar over $20," which ruled this out.
  (Note for future reference: a heavy session like the one that built this
  installer could plausibly approach ~$20 of premium-API tokens on its own -
  which is exactly why, if the API path is ever chosen, it should be a SURGICAL
  tool with a hard prepaid cap, not the default channel.)

### The privacy caveat (conscious tradeoff)
The Gemini free tier may use submitted data to improve Google's models. For the
user's own hobby code this is acceptable, but it IS the reason this is a real
exception to the self-hosted principle - not a costless one. Named so the choice
stays conscious.

### VRAM note (now mostly moot for coding)
Because coding routes off-site, it uses **zero local VRAM** - it never disturbs
image gen, vision, or chat. (Recorded model sizes, for the other groups' sake:
chat qwen3.5:9b ~6.6 GB, vision gemma3:12b ~8.1 GB, embed nomic-embed-text
~0.27 GB, on a 12 GB RTX 4070. The image stack - diffusion ~5.9 GB + text encoder
~5.4 GB - is the real VRAM hog and the thing that must never share VRAM with a
second large model. A specialized coding model, IF ever used locally, holds its
OWN conversation about the code - no parallel chat model needed - and the tiny
embedding model for RAG coexists with it fine; the conflict is only with image
gen and vision.)

### The mode toggle (companion-side design)
A selector in the "talk to Buddy" box puts Buddy in **coding mode**:
- In coding mode -> requests route to the coding channel (Gemini free tier).
- Otherwise -> the standard local model set.
- The mode is a SESSION state (set by the toggle, sent with each request), not
  re-declared per message. It's the natural place to also apply (or drop) the
  Buddy persona for coding, and - if a local coder is ever used instead - to
  signal "safe to unload the other models now."
- Home Assistant / remote callers don't send the flag, so the brain defaults to
  the standard model for them (correct - you don't code through HA).
- Brain-side: add a code path alongside the existing CHAT_MODEL / VISION_MODEL
  selection; pick the channel per-request from the mode flag.

### Dependency on Group 1
Pairing coding with terminal + filesystem access is what lets Buddy actually DO
things, not just suggest code - the user's "trustworthy enough" bar. Gate that
combo carefully (confirmation, scoping, read-only first).

## Suggested sequencing (not binding)

- **Independent, can go anytime:** Web search (low effort, high daily value);
  finishing Vision (partly built).
- **One deliberate infrastructure build:** the Group 2 retrieval backbone -
  unlocks memory + private docs + big references together.
- **High-power, high-risk, gate carefully:** terminal + filesystem, then wiring
  the coding channel (Gemini free tier) + the coding-mode toggle on top.

Nothing here blocks anything else except within a group. Web search and vision do
NOT wait on the retrieval backbone.
