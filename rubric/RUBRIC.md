# Class Quality Rubric (3 layers)

One scoring guide for both human reviewers and the AI scorer, so their ratings
are comparable. The machine-readable version is [`rubric.yaml`](rubric.yaml);
the tier logic lives in [`../scoring/tier.py`](../scoring/tier.py).

| Layer | What it checks | Output |
|---|---|---|
| 1. Must-haves | Background, camera/face, lighting, AV clarity | pass / partial / fail per gate |
| 2. Teaching quality | 8 dimensions of how the class is taught | 1–5 per dimension → weighted score |
| 3. Validation | Do the tiers match reviewers now, and outcomes later? | Agreement reports |

---

## Layer 1: Must-haves

Score each gate **pass / partial / fail**. Measured on frames sampled every 10 s.

| Gate | Severity | Pass | Partial | Fail |
|---|---|---|---|---|
| 8×8 chessboard background | Critical | ≥ 90% of frames | 50–90%, or switched off for part of the class | < 50% |
| Camera on, face visible | Critical | Face in ≥ 90% of frames | 50–90% (camera off at times) | < 50% |
| Lighting | Minor | Face clearly lit | Dim at times, still recognisable | Dark / washed out most of the class |
| Audio & video clarity | Minor | Intelligible, no persistent glitches | Occasional dropouts or glitches | Frequent dropouts, unintelligible, broken background |

**Effect on the tier**
- Critical gate **fail** → tier is **Quality issue**, whatever the Layer 2 score.
- Critical gate **partial** → tier capped at **Weak**.
- Minor gate **fail** → tier capped at **Average**. A minor partial is noted in feedback only.

---

## Layer 2: Teaching quality

Score each dimension **1–5**. The anchors describe 1, 3 and 5; use 2 or 4 for
in-between. **Every score must cite evidence**: timestamps with quotes, or counts.
If there isn't enough evidence, say so rather than guessing.

### Warm-up and rapport (weight 15)
- **5:** Greets each child by name, small talk before teaching, new joiners introduce themselves.
- **3:** Generic greeting, brief chat; new joiners acknowledged but not invited to introduce themselves.
- **1:** Starts teaching or revising straight away, no greeting or rapport building.
- *Measure:* minutes of non-teaching talk before the first content; share of students greeted by name; new-joiner intros (yes / no / none present).

### Inclusion of every student (weight 15)
- **5:** Every student called on by name at least twice; no child silent all class.
- **3:** Most students called on; one or two quiet children left out.
- **1:** Only a few students take part; the tutor addresses the class as a whole.
- *Measure:* distinct students addressed ÷ students present; fewest turns any student had; students who never spoke.

### Students do the thinking (weight 10)
- **5:** Students solve positions and suggest moves most of the time; the tutor guides.
- **3:** Mix of demonstration and student solving.
- **1:** The tutor demonstrates throughout; students only watch.
- *Measure:* student talk time ÷ total talk time; positions where a student proposed the move.

### Questioning (weight 10)
- **5:** Mostly open questions ("What would you play here, and why?"), waits 3+ s, follows up on answers.
- **3:** Some open questions; short waits; occasional follow-ups.
- **1:** Few questions, mostly yes/no; the tutor answers their own questions.
- *Measure:* questions per 10 min; share open; median wait time; uptake (tutor builds on a student's answer).

### Feedback to students (weight 10)
- **5:** Specific praise for effort and ideas; wrong moves corrected by explaining why.
- **3:** Generic praise ("good"); corrections without explanation.
- **1:** Little feedback, or dismissive / discouraging corrections.
- *Measure:* praise count and share that is specific; corrections that give a reason.

### Energy and tone (weight 15)
- **5:** Lively, warm, varied voice; encouragement throughout; kids sound engaged.
- **3:** Friendly but flat or monotone in parts.
- **1:** Low energy, monotone or impatient.
- *Measure:* pitch variation and speaking rate; encouraging phrases per 10 min; tone judgement with quoted examples.

### Lesson structure (weight 15)
- **5:** States today's topic, revises the previous class *after* the warm-up, recaps at the end, sets homework.
- **3:** Clear topic but misses the recap or the homework.
- **1:** No clear topic, no recap, no homework.
- *Measure:* timestamps for topic, revision, recap; homework set (yes / no, with quote).

### Chess clarity (weight 10)
- **5:** Explains why moves work, correct terms, pitched at the kids' level; may use topic videos.
- **3:** Mostly correct, but explanations are thin ("just play this").
- **1:** Confusing or incorrect explanations, wrong level for the class.
- *Measure:* explanations that give a reason; correct use of chess terms; supporting material shown.

---

## From scores to a tier

1. **Layer 2 score** = weighted mean of the 8 dimensions (1–5).
2. **Starting tier:** Excellent ≥ 4.2 · Good ≥ 3.5 · Average ≥ 2.8 · Weak below that.
3. **Caps** (the tier can only go down):
   - Homework not set → at most **Good**.
   - Rapport scored 1–2 → at most **Average**.
   - Layer 1 gate effects, as above.

Tiers: **Excellent · Good · Average · Weak · Quality issue**.

"Informed about quality issues several times" is tutor history, not something in
the recording. Track it as a separate **repeat-issue flag** from tutor records.

---

## Layer 3: Validation

1. **Against reviewers (now).** [`calibration/reviewed_classes.yaml`](calibration/reviewed_classes.yaml)
   holds the 10 reviewed classes. Their scores are currently *inferred from the
   written feedback*; they show the tier rules reproduce the reviewers' tiers
   (`python3 -m unittest`). Next: a reviewer watches each recording and scores it
   with this guide, then the AI scores the same recordings and we compare.
   Target: the AI is within one tier of the reviewer on ≥ 90% of classes and exact on
   ≥ 70%, which is roughly how often two reviewers agree with each other.
2. **Against outcomes (later).** Once there are enough scored classes, check which
   dimensions predict renewals, attendance, parent feedback and student progress,
   and adjust the weights.

Grow the calibration set to **30–50 classes**, covering every tier, before
relying on AI tiers without a human check.

---

## Instructions for the AI scorer

Inputs: transcript with speaker labels and timestamps, the student list, frame-check
results for Layer 1, and audio metrics.

- Score one dimension at a time, using only the anchors above.
- Quote the transcript with timestamps for each score; give counts where the *Measure* line asks for them.
- If the evidence is missing or unclear, return `"score": null` with a reason instead of guessing.
- Do not assign the tier yourself; `scoring/tier.py` does that from your scores.
- Write feedback in the reviewers' style: short phrases, strengths first, then "should …" / "need …" items, each tied to a gate or dimension.

Output per class:

```json
{
  "class_id": "B491-2026-06-29",
  "gates": {"background": "pass", "camera_face": "pass", "lighting": "pass", "av_clarity": "pass"},
  "homework_set": true,
  "scores": {
    "rapport": {"score": 4, "evidence": ["00:01:10 'Hi Arjun, how was school?'", "..."]},
    "...": {}
  },
  "feedback": "good one-to-one interaction, background was there, asked questions individually, ..."
}
```
