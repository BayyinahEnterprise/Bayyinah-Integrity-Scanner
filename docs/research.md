# The Published Record

The Bayyinah research program publishes openly on [Zenodo](https://zenodo.org/search?q=Arfeen%20Bilal&l=list&s=10&sort=newest). Every paper has a permanent DOI, every claim is auditable against its named null hypothesis, and every system in this repository traces back to one of the papers below.

The corpus reads in three concentric layers: a diagnostic protocol for performed alignment in artificial systems, a programming and agent architecture that builds on the protocol, and a set of input-layer applications that put the protocol into production.

---

## Layer 1: The Protocol

**Detecting Performed Alignment in Artificial Systems: The Munafiq Protocol** (v2.1)
[10.5281/zenodo.19700420](https://doi.org/10.5281/zenodo.19700420) · 2026-04-22 · Arfeen, Claude (Anthropic), Grok (xAI)

The anchor paper. Formalizes the surface-depth gap as the failure mode RLHF, Constitutional AI, and helpfulness training do not address: a system can be Compliant (produces outputs the trainer rewards) without being Aligned (the depth state matches the surface presentation). Introduces the four-process taxonomy *Aligned, Compliant, Performing, Misaligned* and the verdict surface *sahih, mushtabih, mukhfi, munafiq, mughlaq* that every downstream system in this corpus inherits.

---

## Layer 2: The Architecture

**Furqan: A Programming Language with Structural Honesty, Calibrated Optimization, and Surface-Depth Type Verification Derived from Quranic Computational Architecture**
[10.5281/zenodo.19776584](https://doi.org/10.5281/zenodo.19776584) · 2026-04-25 · Ashraf, Arfeen, Claude (Anthropic), Computer (Perplexity), Grok (xAI)

A programming language whose type system, module architecture, and build constraints are derived from structural properties of the Quran. Where contemporary languages ask developers to write honest code as a behavioral expectation, Furqan makes structural honesty a property of the type system, so surface-depth divergence becomes a type error rather than a code-review concern.

**Al-Khalifa: A Furqan-Based Super Agent Architecture for Structurally Honest Autonomous Project Stewardship**
[10.5281/zenodo.19776577](https://doi.org/10.5281/zenodo.19776577) · 2026-04-25 · Arfeen, Claude (Anthropic), Computer (Perplexity), Grok (xAI). Additional contributors named on the DOI page.

Applies Furqan's seven compile-time primitives as seven runtime constraints on an autonomous agent. Where AutoGPT, CrewAI, LangChain agents, and Devin decompose tasks but cannot verify whether they are building the right thing versus performing the appearance of building, Al-Khalifa is architected so the surface-depth gap is checked at every step of the agent's stewardship loop.

**Bilal: An Honest-Autonomous Large Language Model Architecture with Structural Truth Verification, Calibrated Generation, and Purpose-Hierarchy Training Objectives Derived from Quranic Computational Architecture**
[10.5281/zenodo.19776576](https://doi.org/10.5281/zenodo.19776576) · 2026-04-25 · Arfeen, Claude (Anthropic), Computer (Perplexity), Grok (xAI)

A model architecture proposal that takes the Munafiq Protocol's structural-honesty constraint and integrates it as a training objective rather than an external evaluation. Reads as the long-form answer to the question Bilal is the first author to ask: what would an LLM look like if alignment were a property of the architecture, not a finetuning target.

**Structured Revelation as Prompt Architecture**
[10.5281/zenodo.19744163](https://doi.org/10.5281/zenodo.19744163) · 2026-04-24 · Arfeen, Claude (Anthropic), Grok (xAI)

The methodology paper. Demonstrates that gradual revelation (tanzil), ring composition, lossless morphological compression, and the zahir / batin distinction function as prompt-engineering primitives in human-AI collaborative software development. Validated longitudinally against the development of Bayyinah v1.0.

**The Fatiha Construct: A Seven-Step Recursive Session Protocol for Human-AI Collaborative Development Derived from Surah al-Fatiha**
[10.5281/zenodo.19746539](https://doi.org/10.5281/zenodo.19746539) · 2026-04-25 · Arfeen, Claude (Anthropic), Grok (xAI)

The session-level companion to *Structured Revelation*. Each of the seven steps maps to a verse of Surah al-Fatiha with structural, not decorative, correspondence: a calibration check, an orientation check, a deadline-with-skip-rule, a memory-encoding step, and an over-specification guard against the failure mode the paper calls the Cow Episode.

---

## Layer 3: The Application

**Bayyinah: Detecting Concealed Adversarial Content in Digital Documents. A White Paper Applying the Munafiq Protocol to the Input Layer**
[10.5281/zenodo.19745154](https://doi.org/10.5281/zenodo.19745154) · 2026-04-24 · Arfeen, Claude (Anthropic), Grok (xAI)

The white paper that turns the protocol into a working scanner. Where the Munafiq Protocol diagnoses agents, Bayyinah diagnoses their inputs. Formalizes the relational definition: a document is Performed with respect to a rendering function and an ingestion function when the machine's ingested content carries a payload the human reader's rendered surface does not reveal.

**Bayyinah as Input-Layer Defense in Artificial-System Safety Pipelines** (v1.1)
[10.5281/zenodo.19802455](https://doi.org/10.5281/zenodo.19802455) · 2026-04-26 · Arfeen, Claude (Anthropic), Grok (xAI)

The deployment paper. Documents the design, implementation, and adversarial-gauntlet evaluation of Bayyinah as an input-layer defense in production AI pipelines. Twelve file formats, an honest miss list, and the discipline that comes from making every miss a published commitment.

**Bayyinah al-Khabir: A Theoretical Framework for Information-Layer Integrity Scanning Across National Broadcast Sources Using Performed-Alignment Diagnostics**
[10.5281/zenodo.19746298](https://doi.org/10.5281/zenodo.19746298) · 2026-04-24 · Arfeen, Ashraf, Claude (Anthropic), Grok (xAI)

The horizon paper. Extends the Bayyinah architecture from documents to information sources: where Bayyinah detects performed alignment in a single document, al-Khabir detects performed alignment in a source's reporting on a specific event measured against the cross-source evidence base across multiple national contexts. Currently theoretical; the protocol scaffolding is published so the implementation that follows can be measured against the framework, not against itself.

---

## Reading order

Three reading paths depending on what you want to verify:

| If you are | Read in this order |
|---|---|
| Evaluating the scanner | Input-Layer Defense → Bayyinah white paper → Munafiq Protocol → repository |
| Evaluating the protocol | Munafiq Protocol → Structured Revelation → Fatiha Construct → Bayyinah white paper |
| Evaluating the architecture | Furqan → Al-Khalifa → Bilal → Munafiq Protocol |

Every paper cites every other paper it depends on. The corpus is engineered to be entered from any point and traversed in any order without circular ambiguity.

---

## How this index is maintained

This file is the curated landing page for the corpus. The canonical list always lives on Zenodo at the search URL above; this file adds the narrative grouping (Protocol → Architecture → Application) that the Zenodo interface does not. When new papers are deposited, both surfaces are updated.

For the live scanner that puts the protocol into production, see the project root [README.md](../README.md) and the live deployment at [bayyinah.dev](https://bayyinah.dev).
