# Trove — Product Plan

**Working promise:** Save the interesting thing now. Find it later by remembering what it looked, sounded, or meant.

> **Current implementation scope (2026-10):** Trove uses embeddings only for model-backed features. Text and image embeddings power semantic search, related memories, and resurfacing. Vision descriptions, OCR, summaries, transcription, topic/entity generation, and generated answers are not current product capabilities; older feature ideas below are exploratory, not implemented behavior.

## Product read

The problem is real, but “save links and let AI organize them” is already a crowded promise. Reddit users recommend Raindrop, Pocket, Obsidian, Readwise, and other tools for pieces of it. Trove has a sharper opening if it owns the cross-format memory: a screenshot, a social post, a voice thought, and a YouTube moment can all be saved to one private place and retrieved without remembering where they came from.

The product should optimize for **recall**, not for building a tidy archive. A useful way to frame it is “save ideas, not just content”: preserve the source and the cues that will help the user reconnect with the idea later. The most important AI feature is not automatic tagging by itself; it is finding the right original item from a vague human recollection, connecting it to related memories, and showing why it matched.

### Sharper problem statement

People use platform-specific saves as a promise to their future selves: “I’ll remember this.” But later they remember a fragment—the idea, a visual detail, an address, or when they saw it—not the app, title, or exact search words. The saved item is separated from both its context (“why this mattered”) and its next action (“use this for a project”). As the pile grows, search and infinite scrolling break down, while manual organization asks people to do extra work at exactly the moment they are trying to capture something quickly.

Trove's job is to preserve a **retrieval cue** with each Memory, retrieve it from an imperfect recollection, and help the user act on it. That is more valuable than simply centralizing links or auto-assigning categories.

## User and job

### First user

A curious, heavy saver who collects ideas from social apps, videos, the web, screenshots, and their own thoughts. They save things several times a week, forget which app contains a particular item, and do not want a daily filing routine.

### Job to be done

> When I see or think of something I may want later, let me save it immediately with its useful context, then help me retrieve it using the words, image, topic, source, or time I remember.

### Promise to keep

1. Saving takes one quick action and works when offline.
2. Every memory stays searchable even if the user never organizes it.
3. Trove shows the source and what it actually captured; it never pretends a link is a durable copy.
4. Private by default, with clear controls for cloud processing, retention, export, and deletion.

## What Reddit users say

This is a small qualitative sample of public threads, useful for shaping hypotheses rather than measuring market size:

- In [“App for saving bookmarks and screenshots?” on r/productivity](https://www.reddit.com/r/productivity/comments/145ri1a/app_for_saving_bookmarks_and_screenshots/), the poster wanted an archive for later reference rather than a read-later queue, and wanted visual previews to recognize saved links. Replies repeatedly named Raindrop and Pocket, suggesting that link storage alone is not a differentiator.
- In [“How do you keep track of everything you save across X, Instagram and bookmarks?” on r/ObsidianMD](https://www.reddit.com/r/ObsidianMD/comments/1u08orz/how_do_you_keep_track_of_everything_you_save/), the poster describes saves scattered across apps, forgetting why they saved things, and not wanting to maintain a system. Replies specifically recommend capturing “why I cared” in one sentence and warn that organizing everything later becomes a second chore.
- In [“Saved posts on Instagram are great… until you actually try to find old one” on r/Instagram](https://www.reddit.com/r/Instagram/comments/1qa03go/saved_posts_on_instagram_are_great_until_you/), a user with thousands of saves calls out missing date sorting and filters, slow infinite scrolling, and lost scroll position. A commenter says the backlog is so overwhelming they plan to stop saving.
- In [“Ai Sort Bookmarks?” on r/PKMS](https://www.reddit.com/r/PKMS/comments/1qmixcw/ai_sort_bookmarks/), a user asks for intelligent categorization because existing options feel expensive. Replies also question whether sorting is needed at all and point out that search can be enough. This is a useful warning against making AI filing the main product.
- In [“how do you save and find useful content later?” on r/ObsidianMD](https://www.reddit.com/r/ObsidianMD/comments/1sznehr/how_do_you_save_and_find_useful_content_later/), a user says they remember the rough idea but lose the details. Replies contrast collecting content with saving ideas, recommend adding a brief “why I cared” or “use this when” cue, and describe semantic search as useful when the remembered words differ from the saved text.

### Product implications

- Unify the inbox across sources and media types.
- Preserve source, time, content type, topics, entities, and relationships automatically. If Trove infers why something might matter to a person, phrase it as a tentative explanation and keep it separate from anything they wrote themselves.
- Provide chronological navigation and strong search so an old item is not buried in an endless stream.
- Auto-extract topics for retrieval, but do not make users maintain tags or folders.
- Make the original source easy to reopen and clearly distinguish a link from a saved snapshot or extracted copy.

## Spaces: optional structure that stays out of the way

Spaces give people a few familiar places to group memories, such as **Ideas**, **Notes**, **Game tips**, or **Passwords**. They are useful when someone wants to organize, but they should never be the destination users must choose before saving.

- Every new memory goes to **All memories / Inbox** by default.
- A memory can belong to zero or more Spaces; adding it to a Space never removes it from the main stream.
- Saving from inside a Space adds the new Memory there automatically; saving from the general capture flow goes straight to All Memories.
- Users can add or remove a Memory from Spaces later from its detail screen.
- Trove may suggest a Space after saving, but it should ask for a lightweight confirmation and make dismissal easy. Do not silently move or hide memories.
- Keep AI-detected topics (for example, “generative AI”, “typography”, “recipes”) as searchable metadata. Show them as editable suggestions, not required tags.
- Search works across all Spaces by default; users can narrow it to one Space.

**Decision:** Include a minimal Spaces layer in the first useful release, but make it subordinate to Inbox and search. Do not build nested folders, rule builders, or a tagging workflow in the MVP.

## Core object: Memory

Each Memory should retain the original item and its context, not just a note title:

- Original file or captured input, when provided by the user.
- Canonical URL and source app/site, when available.
- Capture time and original publication time, when available.
- Preview: image, thumbnail, or extracted text.
- Extracted content: OCR, transcript, title, description, and detected people/objects/topics where useful.
- Optional user context: a short note or voice thought explaining why it matters.
- AI-generated description and search index, with provenance shown in detail.
- Optional Space membership and user corrections.
- Capture status: link only, file saved, text extracted, or processing failed.

Keep both the original and any generated metadata visible in the detail view. Users must be able to correct a wrong title, topic, or transcript and to export their library.

## Feature plan

### P0 — The reliable save-and-find loop

**Capture**

- Native share target for links and text, starting with the primary mobile platform selected by early user research.
- Save images and screenshots from the share sheet and camera roll.
- Quick text capture and in-app voice memo recording.
- Offline capture queue: confirm locally that an item is saved, then sync and process when connectivity returns.
- Show an honest confirmation immediately, with processing status available afterward.

**Understand**

- Web links: title, domain, thumbnail, accessible page text, and a short summary.
- Images: OCR plus a concise visual description.
- Voice memos: transcript and short summary.
- YouTube: title, creator, thumbnail, transcript when available, and searchable timestamped transcript segments. Search results should deep-link to the matching moment. Save the link and transcript; do not imply that Trove has downloaded or owns the video.
- Social links: retain the URL and any text/media the operating system or user actually shared. If Trove cannot access the content, say so and offer a screenshot or pasted-text fallback. Do not promise a permanent copy of every Instagram, Reddit, or other protected post.
- Processing failures never discard the original capture.

**Find**

- One search box across text, OCR, transcripts, titles, summaries, and AI descriptions.
- Semantic and keyword search together; exact phrases and source names must still work.
- Filters for date, source, media type, and Space.
- Visually scannable results with image previews, text snippets, source, and date.
- Example queries: “that dark website with huge white type”; “the screenshot about AI agents in Unreal”; “the YouTube bit where she explains evals”.

**Browse**

- All Memories timeline, newest first, with predictable date navigation and no forced triage.
- Inbox for recently saved or still-processing items.
- A small Spaces list, quick-start names, and basic Space pages with type filters.
- Memory detail: saved content, source link, extracted text/transcript, note, topics, and capture status.

### P1 — Make retrieval feel like remembering

- Browser extension for one-click saving while reading on desktop.
- Import/export for bookmarks and common file formats; bulk import with progress and duplicate handling.
- User-approved related Memories and topic clusters, with a clear reason for each suggestion.
- Optional weekly resurfacing digest and date-based “Your October” review. Let people control frequency and turn it off.
- Basic grounded Ask: answer from the user's own saved material, link each claim to the matching Memory, and say when the library does not contain the answer.
- More robust handling for PDFs, documents, and longer audio.

### P2 — Expand after repeat use is proven

- Cross-memory synthesis and unexpected-connection discovery.
- Smart resurfacing based on projects, time, and user behavior.
- External topic monitoring: follow selected subjects, sources, or creators and receive a low-noise digest of new public material. Treat this as a separate opt-in product surface, not the default meaning of “related.”
- Shared Spaces or collaborative libraries, only if research shows a real multi-person job.
- Advanced workflows, automations, nested Spaces, and custom tag systems.

## App structure for design

1. **Home / All memories:** search at the top, recent captures underneath, Spaces accessible but not dominant.
2. **Inbox:** new and processing items, with clear save status. Triage is optional.
3. **Search:** query field, natural language suggestions, filters, and results that show the matched text or timestamp.
4. **Memory detail:** source, preview, extracted information, original content, optional “Why I saved this” note, and edit/correct actions.
5. **Space:** name, optional description, member Memories, and search within the Space.
6. **Explore:** resurfacing and related memories; keep it quiet until search and capture are dependable.
7. **Settings:** privacy and AI processing, offline/sync status, storage, export, and account controls.

### Main flows to prototype

**Save a social post:** Share → Trove → confirm saved to Inbox → background extraction or honest link-only status → optional Space suggestion.

**Save an idea:** open quick capture → type or dictate → save immediately → transcript appears later → optional add to a Space.

**Find a memory:** describe what is remembered → see matching image/text/time/source and why it matched → open saved item or original source.

**Create a Space:** name it and optionally describe its purpose → add existing Memories in bulk or accept future suggestions → continue to search across the whole library.

## MVP boundary and recommended build order

Do not start with every modality and an elaborate AI assistant. Prove the habit and retrieval loop in this sequence:

1. One-tap capture of URL, text, and image into a persistent Inbox, including offline queueing.
2. Useful previews, OCR, metadata extraction, and processing status.
3. Hybrid search across saved text and OCR with source/date filters.
4. Voice capture/transcription and YouTube transcript search with timestamp links.
5. Minimal Spaces and optional topic suggestions.
6. Quiet, opt-in resurfacing of older saves that connect to newer ones.
7. Broader file ingestion, browser extension, and grounded Ask after repeat use is visible.

If voice is central to the first audience, move voice capture ahead of Spaces. Do not claim the full “save anything from any app” promise until each platform/source path has been tested and its limits are clear.

## Privacy, reliability, and trust requirements

- Private by default; do not create public sharing or social features in the first release.
- Explain what is uploaded for AI processing and offer a local-only or reduced-processing mode if technically feasible.
- Retain original user-provided files and links even when enrichment fails.
- Make deletion, bulk export, and account data controls easy to find.
- Avoid training on personal memories by default; disclose any provider retention limits plainly.
- Mark whether a result comes from the original shared file, extracted text, a cached snapshot, or AI-generated interpretation.
- For third-party pages that require login or block extraction, save a link and let the user add a screenshot or text. Never disguise this as a durable archive.

## Business model hypothesis

Automatic understanding and basic retrieval need to be present in Free; otherwise people will not experience the core promise. Monetize deeper memory, higher limits, and integrations rather than making users pay to avoid manual filing.

- **Free — Memory (₹0):** capture across devices, automatic classification and topics, keyword and basic semantic search, basic OCR, light resurfacing, and import/export, within a modest storage limit.
- **Plus — Deep Memory (₹129–199/month hypothesis):** substantially more storage, full-text/OCR search across files, visual search, richer connections, advanced resurfacing, summaries, and preserved web pages.
- **Pro — Context (₹799–1,499/month hypothesis):** let a user's AI tools search and retrieve their Trove through MCP; add write access only after the read experience is trusted.

These prices are hypotheses, not validated willingness to pay. Keep the basic save-and-find loop useful for free, then test paid tiers with frequent savers after the product demonstrates repeat retrieval. Professional editions for developers, designers, founders, and researchers—and a broader API—are later packaging options, not MVP requirements.

## What to measure

- **Capture success:** share-to-confirm completion rate; time from share action to local save confirmation; failed or duplicate capture rate.
- **Recall success:** searches that open a result; time to the correct Memory; zero-result rate; user feedback on whether the intended item was found.
- **Habit:** weekly active savers, captures per active user, and repeat retrieval within 7/30 days.
- **Organization burden:** proportion of captures needing a manual tag/Space action; abandonment during save; Space suggestion accept/dismiss rate.
- **Trust:** extraction correction rate, link-only rate by source, processing failure rate, export/deletion completion.
- **Business:** free-to-paid conversion and retention only after the core loop demonstrates repeat value.

The north-star metric should be **successful retrievals per weekly active saver**, paired with capture success so Trove does not encourage saving for its own sake.

## Key risks to validate

1. **Platform access:** Share sheets often provide less content than users expect, and social sites change what can be fetched. Prototype Instagram, Reddit, and YouTube capture paths on actual devices before promising durable content copies.
2. **Capture breadth versus quality:** Supporting every file type can delay a dependable first save flow. Start with the sources that first users actually save most.
3. **AI noise:** Incorrect tags, summaries, or visual descriptions erode trust. Make generated fields editable and keep raw content searchable.
4. **Space creep:** If users must choose a Space or tag on every save, Trove recreates the organization burden it promises to remove.
5. **Weak return loop:** Users may save often but rarely revisit. Test real retrieval tasks and resurfacing with existing personal libraries, not just demo content.
6. **Privacy-cost tradeoff:** Users may reject cloud processing of private screenshots or voice. Test local and cloud processing expectations early.

## Research next steps

- Interview 8–12 frequent savers and ask them to show their last 10 saves, where each lives, and how they would retrieve one a month later.
- Have them try three clickable prototypes: save with no filing, optional Space suggestion, and mandatory categorization. Measure speed and preference without leading them.
- Test a real corpus of mixed screenshots, links, YouTube clips, and voice notes with vague retrieval prompts. Track whether semantic search returns the intended item and shows the right evidence.
- Ask what they would trust Trove to preserve versus merely link to, and which content they would allow cloud AI to process.
- Validate the target launch platform and the $8–12 Pro range before committing to architecture and pricing.

## Similar memories, resurfacing, and updates

These should be three distinct capabilities with different labels and controls:

### 1. Similar memories — connect items in the user's own Trove

This is the natural next step after save and search. Use the saved item's text, OCR, transcript, visual description, and any user context to find other memories in the same personal library. Surface it on the detail screen as **“Related in your Trove”** or after save as a quiet follow-up. Do not interrupt the save confirmation.

- Separate **same item**, **similar idea**, and **same topic** so a duplicate does not look like a new insight.
- Explain the match in one short line: “Both are about using procedural generation in Unreal.”
- Show source, date, and a preview for each related Memory; tap through to the original.
- Offer “Not related” / dismiss, and let that feedback improve future ranking.
- Hide low-confidence matches. An empty state is better than noisy recommendations.
- Provide privacy controls for using personal Memories to generate recommendations.

### 2. Resurfacing — bring the user's own older saves back at a useful time

This can serve the “keep me updated” need without turning Trove into another content feed. Start with a quiet, opt-in weekly recap: a few older memories related to recent saves, a revisit date such as “On this day,” or a cluster that has become more interesting as new memories were added. Say **why now** and let the user snooze, dismiss, or reduce frequency. Avoid daily notifications, streaks, and guilt-driven “inbox zero.”

### 3. External updates — monitor the wider web for new material

This is a different, much larger job. If people mean “tell me when something new appears about this topic,” let them explicitly create a **Watch** from a topic or Space, choose sources and cadence, and review deduplicated results with source links and a short “why this matches” explanation. Keep it muted by default until a meaningful result exists.

Do not bundle web monitoring into the first release. It requires source coverage, freshness, deduplication, ranking, notification controls, and a clear line between saved personal knowledge and external search. A cheaper test is an opt-in weekly digest based on a small set of feeds or sources chosen by the user. If most people want new content discovery more than recovery of their own saves, revisit Trove's positioning before building a general feed.

## Make a Memory useful in the real world

Trove can keep a universal Memory model while showing small, type-specific actions when the content supports them. These actions make “I saved this” more useful without turning the app into several specialized products.

- **Pinterest inspiration:** retain the Pin link and image/preview, then show related designs from the user's own Trove.
- **Recipe:** preserve the source, extract ingredients and steps when possible, and add a “cook later” action only if a real cooking workflow is in scope.
- **YouTube:** search inside the transcript and open the exact timestamp, rather than returning only a video title.
- **Voice thought:** keep the playable audio, transcript, and original capture time together.

The address example is a useful design stress test, not evidence from the Reddit sample that address capture is the top unmet need. A related public thread, [“The ‘Copy-Paste’ struggle is ruining my China trip planning” on r/chinatravel](https://www.reddit.com/r/chinatravel/comments/1rt3vtw/the_copypaste_struggle_is_ruining_my_china_trip/), describes the gap between a recommendation and getting a usable location into a map app. This suggests a useful general pattern: preserve the source Memory, extract an actionable entity, and offer a clear handoff.

## Product value proposition

### Recommended positioning

> **Trove is your private memory for the things you find interesting. Save links, screenshots, videos, and voice notes in one place—then find them later by what you remember, not where you saved them.**

This is specific about the job and the difference. “AI-organized,” “all-in-one workspace,” and “save anything” are weaker because many products can claim them and platform access may limit what Trove can truly preserve.

### Short copy to test

- **Save what catches your attention. Find it when it matters.**
- **Your saved things, remembered.**
- **A private memory for everything you mean to come back to.**

Show one concrete retrieval example in onboarding and the store page: “Find the screenshot with the dark site and huge white type.” Demonstrate the matching result, not a row of abstract AI features.

## High-quality capture and retrieval UX

### Capture should feel nearly invisible

- Make the operating-system share action the main entry point. Avoid sign-up, Space choice, tags, and summary review in the save path.
- Show a small confirmation immediately: **Saved to Trove**. Include Undo and destination if applicable.
- Process in the background. Later, show “Transcript ready” or “Couldn’t read this page” in Inbox/detail without losing the original.
- Keep Space choice optional. If suggesting one, do so after the save and explain it in one tap.
- Offer quick capture from Home for thoughts that are not being shared from another app.

### Search is the primary navigation

- Put one forgiving search field at the top of Home. Support plain language, exact phrases, visual descriptions, dates, source names, and mixed queries.
- Return the best result first, with the exact matching text, OCR snippet, or video timestamp visible. Let users refine with source/type/date/Space chips instead of requiring search syntax.
- Give visual and text list layouts equal care; never make image-only results impossible to scan with accessibility tools.
- Keep the original source one tap away, and label the capture status on the card.

### Keep the visual system calm

- Use a consistent card skeleton for all Memories: preview, type/source, title or first line, capture date, and a small status/topic indicator.
- Let the media create the card's visual identity; avoid filling cards with AI summaries, tag clouds, and metadata badges.
- Prioritize content and search results over dashboards, engagement metrics, or a busy Explore feed.
- Provide strong empty, offline, processing, permission, and extraction-failure states. Each should explain the next useful action in plain language.
- Make Undo, correction, export, and deletion discoverable so the user stays in control of their archive.

### Screen priorities

1. **Home:** search, capture affordance, recent Memories, and a restrained Spaces entry.
2. **Share success:** brief confirmation with Undo; no blocking AI animation or required follow-up.
3. **Search results:** clear matches, visible evidence, and low-friction filters.
4. **Memory detail:** original plus extracted understanding, related Memories, optional user context, and source actions.
5. **Explore / resurfacing:** opt-in and secondary; show a small number of explainable suggestions.
6. **Watch settings (later):** sources, cadence, quiet hours, mute and remove controls, plus a preview of what will be monitored.

## Keep the feature set legible

Use these user-facing concepts consistently:

- **Memory:** one saved thing and its context.
- **Space:** an optional user-chosen context or project.
- **Topic:** system-detected and searchable; editable, never required.
- **Related:** other Memories in the user's own library.
- **Resurfaced:** an older Memory brought back with an explanation.
- **Watch:** an explicit request to find new external material.

Avoid using “recommendations” for both personal archive matching and external web results. Users should always know whether Trove is showing their own saved material or new content from elsewhere.
