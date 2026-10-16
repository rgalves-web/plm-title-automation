# PLM Title Automation

The language of title research and examination work for Purple Land Management (PLM): turning scattered documents into grounded deliverables, with a trail that explains every result. Two projects share it: Emirates (due diligence per Unit, DDR deliverable) and Cibola (surface title per Tract, runsheet package).

## Cases and scope

**Case**:
The unit of work that owns a Case File: one Tract or one Unit, with its own identity, approved scope and history.
_Avoid_: job, matter, "unit" when the Case is a Tract

**Case File**:
The persistent record of one Case: identity, scope, documents, searches, claims, reviews, tasks, decisions, deliverable versions, knowledge used, execution records and open items.
_Avoid_: dossier, casefile (one word), conversation history

**Tract**:
A Case kind (Cibola): a surface parcel whose title chain is researched and examined for a surface title report.
_Avoid_: unit, parcel, PID

**Unit**:
A Case kind (Emirates): a pooled production unit whose leases, title opinions and interests are reviewed for a DDR.
_Avoid_: tract, well

**PID**:
A county property identifier that may span several Tracts; it groups Cases and is never itself a Case.
_Avoid_: tract, parcel number

**Stage**:
Where a Case is in its lifecycle, from Indicated through Planning, Collecting, Examining, Verifying, Filling, Auditing and Awaiting Renato to Released, with Blocked reachable from any Stage.
_Avoid_: status, state (unqualified)

**Operational state**:
Whether executors are working a Case right now: paused, running, waiting or finished. A finished Case is not Released; only Renato releases.
_Avoid_: stage, status

**Round**:
A bounded period of execution on a Case that ends in a Disposition.
_Avoid_: run, sprint, session

**Disposition**:
The recorded outcome of a Round or of a document: what finished, what remains executable, which dependencies are proven, and which lessons are proposed.
_Avoid_: status update, summary

## Claims

**Claim**:
A material assertion in a Case File, always carrying its subject, source document, page, literal quote, limitations and review state.
_Avoid_: finding, fact (as the umbrella), statement

**Claim nature**:
What kind of assertion a Claim is: documentary observation, inference, proposed conclusion, divergence, insufficient evidence, open item, or human decision.
_Avoid_: claim type (that is a different axis)

**Claim type**:
What a Claim is about in the Case inventory, such as tract, well, XREF row, document present or document missing.
_Avoid_: claim nature

**Documentary observation**:
A Claim nature: something legible in the source itself.
_Avoid_: fact

**Proposed conclusion**:
A Claim nature: an analytical result derived from observations that still requires its applicable review.
_Avoid_: conclusion (unqualified), finding

**Human decision**:
A Claim nature: a recorded determination by the authorized person (Renato).
_Avoid_: approval (unqualified)

## Documents and research

**Document status**:
How far a document has progressed: located, accessible, captured, saved, examined, incorporated into the deliverable.
_Avoid_: found, done, reviewed

**Capture integrity**:
Whether a capture holds the whole instrument (complete) or not (partial, missing pages, cropped). Only a complete capture can be examined in full.
_Avoid_: quality

**Territorial application**:
Whether a document affects a given Case: demonstrated, excluded with grounds, or undetermined pending a named gap. Assessed separately for each document and Case pair.
_Avoid_: relevance, belongs to

**Documented negative search**:
A search with no hits whose object, criteria, period, source coverage and returned material are all recorded.
_Avoid_: not found, could not be located

## Roles and execution

**Function**:
One of the ten responsibilities in the operation: Coordinator, Researcher, Archivist, Classifier, Examiner, Verifier, Arbiter, Writer, QA, Retrospective.
_Avoid_: agent, worker, role (in prose)

**Executor**:
A process that takes tasks from the queue and runs whichever Function the task names.
_Avoid_: agent, function, worker (in prose)

**Examiner**:
The Function that reads instruments and produces Claims with source, page, quote, application and limitations.
_Avoid_: analyst

**Verifier**:
The Function that independently reads the same source, from a model family other than the producer's, and records what the source supports.
_Avoid_: reviewer, checker

**Call lifecycle**:
The progression of one model call: in progress, response received, valid output, result applied, task completed. A response not yet applied never advances a Case.
_Avoid_: done (for any step short of applied)

## Knowledge

**Case memory**:
The documents, parties, searches, claims, analyses and decisions of one Case. It never becomes a general rule.
_Avoid_: knowledge, lessons

**Reusable knowledge**:
Method, procedure, instruction, review criterion and approved lesson that may apply across Cases within a declared scope.
_Avoid_: memory, facts

**Candidate lesson**:
A proposed piece of Reusable knowledge, with source, interpretation, scope, conditions and exceptions, awaiting Renato's approval or rejection.
_Avoid_: rule, learning

**Publication**:
An immutable, identified version of Reusable knowledge; each execution is pinned to the Publication in force when it started.
_Avoid_: current knowledge, latest

## Client and project terms

**DDR**:
Due Diligence Report, the Emirates per-Unit Excel deliverable.

**TO**:
Title Opinion. Original and Supplements over the same legal description: the most recent by ownership certification "as of" date controls.
_Avoid_: opinion date (use the certification date)

**DPU / DOU**:
Declaration of Pooled Unit / Designation of Unit. Exhibit "A" lists the Unit's leases (the perimeter authority); Exhibit "C" lists the tracts.

**XREF**:
The Lease-to-Well-and-Contract cross-reference workbook (two sheets; both are filtered).

**WI / NRI**:
Working Interest / Net Revenue Interest. A leasehold (TO-derived) versus wellbore (Well List) mismatch is often JOA non-consent uplift, not a defect.

**Supplemental title**:
The chain from the controlling certification date to the present, seller-affecting and of record only.

**Recording reference**:
A multi-county recording string; Cooke reception numbers restart each year and are always paired with the year.

**Runsheet**:
The Cibola surface title deliverable listing the instruments of a Tract's chain, prepared under the Cibola protocol and Derek's confirmed exemplar.
