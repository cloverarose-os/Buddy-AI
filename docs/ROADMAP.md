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
- **Open question:** which search API (there are free/paid options; some need a
  key). Decide based on cost + quality.

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

The hardest to make "genuinely useful" (the user's explicit bar), and the one
capability that RAG and fine-tuning CANNOT manufacture. Coding skill comes from
the base model.

### The three approaches, honestly ranked

1. **Swap in a specialized coding model (RECOMMENDED).** Purpose-built coding
   models (e.g. Qwen-Coder, DeepSeek-Coder families) are dramatically better at
   code than a general 9B. They run via Ollama exactly like the current models.
   This is the real lever for "genuinely useful."
2. **RAG for code (COMPLEMENT, not a substitute).** Letting the model see YOUR
   actual codebase (via the Group 2 backbone) grounds it in your project - useful
   ON TOP of a good coding model, but it does not create coding ability.
3. **Fine-tune the current model (NOT RECOMMENDED).** Expensive, slow, needs a
   training dataset, and realistically won't match a purpose-built coding model.
   Off the table for this goal.

### The real tradeoff to decide
VRAM budget. The machine can only hold so many models loaded at once (chat +
vision + embedding already). A dedicated coding model is either:
- a SWAP (unload chat, load coder when coding), or
- a memory-budget decision (can the GPU hold another large model?).
The RTX 4070 (12 GB baseline) constrains this. Decide swap-vs-coexist when the
feature is actually taken on.

### Dependency
If code coding is paired with terminal + filesystem access (Group 1), that's what
makes it able to actually DO things, not just suggest code. That combo is the
"trustworthy enough" bar the user named - so gate it carefully.

## Suggested sequencing (not binding)

- **Independent, can go anytime:** Web search (low effort, high daily value);
  finishing Vision (partly built).
- **One deliberate infrastructure build:** the Group 2 retrieval backbone -
  unlocks memory + private docs + big references together.
- **High-power, high-risk, gate carefully:** terminal + filesystem, then a
  specialized coding model on top.

Nothing here blocks anything else except within a group. Web search and vision do
NOT wait on the retrieval backbone.
