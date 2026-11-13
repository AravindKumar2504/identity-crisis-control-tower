# The 3-minute demo and the sealed envelope

Draft v1, Fri 11/13. Every line below uses the screen's own wording, and every number comes from the practice envelope as of commit 431de49. Read it aloud with a stopwatch before Saturday, and re-check the lines listed under "Check at Friday's 9 PM dry run".

**Roles (suggested):** Madhu speaks and Aravind drives the laptop. Aakruti and Chirag answer questions on their own parts.

**Before you start:**
- The screen is open (`streamlit run app.py`) with "Envelope practice" picked and the ER-alpha question showing.
- A terminal is open in `identity-crisis-control-tower` with the venv on.
- The browser is zoomed so all 8 question buttons are visible.

## The script (about 380 words, roughly 2:35 of speaking plus clicks)

### 0:00 Hook (20 s) · screen: the verdict card

> A lab gets a new TCGA breast cancer release. Same files, same 747 protein samples. A row count sees nothing wrong. But two samples traded data, five are copies of other samples, and five real ones are gone. Cohort Control Tower catches that, then asks: is this release still fit for your research question?

### 0:20 What changed (60 s) · screen: What changed tab, then Analyses

> We fingerprint every sample in every file, so any change shows up. Here are the three changes, with every affected sample named: twelve samples, and not one that didn't change. That matches the organizers' reference answer for this envelope.

*[Analyses]*

> Only the analysis that reads those samples is rerun. The ER-alpha difference moves from 3.051 to 3.019. Each finding shows its own measured effect: undoing the swap alone moves the result by about 1.2 percent.
>
> So does the conclusion still hold? Yes. The 95 percent range is 2.835 to 3.179, and without the flagged samples it is 3.047. The verdict is Conditional: usable once a person reviews these three findings.

### 1:20 Change the question (60 s) · screen: the question board

> Same release, eight research questions, and the verdict depends on the question.

*[OS, Luminal A]*

> Overall survival in Luminal A: Blocked. Median follow-up is 32.9 months, and the TCGA curators' own paper says overall survival may suit basal-like tumors, but not Luminal A.

*[PFI, Luminal A]*

> The tool suggests progression-free interval, which the curators recommend without reservation, and the block is gone.

*[Subtype classifier]*

> Training a model to predict PAM50 subtype from RNA: Blocked, because the PAM50 label was computed from that same RNA. High accuracy would only show it relearned that rule.

*[Hormone therapy]*

> Hormone therapy response: Blocked. The release doesn't record which tumors got hormone therapy, or any response to it.
>
> Every block names its source, the next step, and the evidence that would change it.

### 2:20 Review and sign-off (30 s) · screen: Review and sign-off tab

> No fix is applied on its own. A person approves, rejects, or asks for more evidence on every proposed fix, and a rejection needs a reason. Sign-off writes a record with the release fingerprints and every decision, in the organizers' shared format, checked by their validator. And if a file is damaged or missing, the tool refuses with Insufficient Evidence instead of guessing.

### 2:50 Close (10 s)

> We tested it on 20 releases, 7 of them built to break it, with every answer key written before the tool ran. 20 of 20 pass. One command, about two seconds. Hand us the envelope.

**If you run over 3:00:** cut the hormone therapy click first. Next, cut the "without the flagged samples" sentence.

## Q&A: the sealed envelope

1. The judge gives a number and four words. Aravind types:

   ```bash
   python -m tower envelope <number> <word1> <word2> <word3> <word4>
   ```

2. Madhu reads three things aloud:
   - the verdict line
   - each finding: its kind, how severe, how many samples, and which analysis it touches
   - the `valid` line (the organizers' validator passed) and the total time
3. Refresh the screen. The opened envelope appears in the release list; pick it and show the question board.
4. **If the command fails:** use the sidebar's "Open a sealed envelope" instead. If that also fails, unseal with the organizers' script, then compare:

   ```bash
   cd ../oncosys-hackathon-challenge && python envelopes/unseal.py <number> <word1> <word2> <word3> <word4>
   ```

   ```bash
   cd ../identity-crisis-control-tower && python -m tower compare ../oncosys-hackathon-challenge/data/tcga-brca/raw ../oncosys-hackathon-challenge/envelopes/opened/<number>/release --challenge ../oncosys-hackathon-challenge
   ```

## Likely judge questions

- **How do you know it's right?** We have 20 of 20 test releases. Thirteen were made with the organizers' own generator and graded against its answer keys. We built the other seven, each with its answer written first (`python scripts/scorecard.py ../oncosys-hackathon-challenge/data/tcga-brca/releases`).
- **What about a change you never planned for?** Any changed value shows up in a fingerprint. If it isn't a swap, a copy or a loss, it's reported as an edit, with every sample named.
- **Why Blocked, not a warning?** Even with perfect files, this data can't support that question. A warning would let someone publish a Luminal A survival result from under three years of follow-up.
- **Is AI making these calls?** No. Every verdict comes from a written rule with a cited source, and a person signs off.
- **Clinical use?** No. It's for research only: no diagnosis, no treatment advice, no risk scores.

## Check at Friday's 9 PM dry run

- **PFI may change.** It shows Ready today only because Aakruti's survival checks aren't built. Once they land it may say Conditional (what PLAN.md expects), so re-read the board and adjust that line. The "Not built yet" text must not appear in front of judges.
- **Hook choice.** If the duplicate-patient check shows TCGA-AN-A0FE and TCGA-AN-A0FG on screen, PLAN.md's hook is stronger: the same patient enrolled twice under two IDs.
- **Timing.** Read it aloud twice with a stopwatch.

## Where the claims come from

- Practice numbers (747 protein samples, 12 samples cited, 3.051 to 3.019, the 1.2 percent effect, the 2.835 to 3.179 range, 3.047 without the flagged samples, 32.9 months): the tool's own output on the practice envelope.
- Endpoint advice: Liu et al., An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive High-Quality Survival Outcome Analytics, Cell 2018, https://doi.org/10.1016/j.cell.2018.02.052. It recommends PFI and DFI without reservation, suggests caution with overall survival in breast cancer, and says overall survival may suit the basal-like subtype but not Luminal A.
- PAM50 is computed from gene expression: Parker et al., Supervised Risk Predictor of Breast Cancer Based on Intrinsic Subtypes, J Clin Oncol 2009, https://doi.org/10.1200/JCO.2008.18.1370.
