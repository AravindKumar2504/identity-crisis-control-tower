# The 3-minute demo and the sealed envelope

Draft v4, Fri 11/13 evening (every check built; Aravind presents). Every line below uses the screen's own wording, and every number comes from the practice envelope. Read it aloud with a stopwatch before Saturday, and re-check the lines listed under "Check at Friday's 9 PM dry run".

**What the judges want (the organizers, Friday 8:55 AM):** every working tool finds the same changes, so show why they matter, what the user should do next, and what the tool can't tell them. The slides add: name your user, show one result a judge can verify and one limitation they can inspect. This script covers each: the user in the hook; the measured effects and the HER2 loss (why it matters); the next steps (what to do); the "What this can't tell you" box (the limitation); and the Analyses view on the Evidence page, where the organizers' own script gives the same number (the result a judge can verify).

**Roles:** Aravind speaks and drives the laptop. A teammate who is there can drive instead, and Aakruti can take questions on the release A checks.

**Before you start:**
- The screen is open (`python -m streamlit run app.py --server.address localhost`) with "Envelope practice" picked and the ER-alpha question showing.
- A terminal is open in `identity-crisis-control-tower` with the venv on, and `python -m tower doctor` ends with "Ready for the sealed envelope."
- The browser is zoomed so all 8 question buttons on the Overview are visible and the top menu shows all five pages (a narrow window folds them into "N more").
- On **Review and sign-off**, a reviewer name and role are filled in. They stay while you move between pages; a browser refresh clears them.
- Old Fool the Tower runs are cleared: delete the `out/fool/` folder (git ignores it), so the release list shows only the envelopes and test releases.

## The script (about 400 words, roughly 159 seconds of speaking plus clicks; the optional hormone therapy click adds about 7 seconds)

### 0:00 Hook (20 s) · screen: Overview, the verdict card

> Our user is a research data engineer, and a new TCGA breast cancer release just arrived. Same files, same 747 protein samples. A row count sees nothing wrong. But two samples traded data, five are copies of other samples, and five real ones are gone. Cohort Control Tower catches that, then asks: is this release still fit for your research question?

### 0:20 What changed (60 s) · screen: the What changed page, then Evidence (Analyses tab), then the Overview

> We fingerprint every sample in every file, so any change shows up. Here are the three changes, with every affected sample named: twelve samples, and not one that didn't change. That matches the organizers' reference answer for this envelope. And the five samples that disappeared are all HER2-enriched tumors, so that subgroup shrinks while the total stays the same.

*[Evidence page, Analyses]*

> Only A1 reads those samples, so only A1 is rerun: the ER-alpha difference moves from 3.051 to 3.019. A2, the subtype mix, is left alone, because nothing it reads changed.
>
> So does the conclusion still hold? Yes, with room to spare: it survives 61 worst-case swaps between ER groups, and this release made one.
>
> *[Overview]* The verdict is Conditional, and every problem comes with a next step: report the hospital mix, because requiring protein data changes which hospitals the tumors come from; restore the swapped profiles; and exclude the copies.
>
> *[point at "What this can't tell you"]* And it says what it can't tell you: which release labels the swapped samples correctly.

### 1:20 Change the question (60 s) · screen: Overview, the question board

> Same release, eight research questions, and the verdict depends on the question.

*[OS, Luminal A]*

> Overall survival in Luminal A: Blocked. Median follow-up is under three years, and the TCGA curators' own paper says overall survival may suit basal-like tumors, but not Luminal A.

*[PFI, Luminal A]*

> The tool suggests progression-free interval, which the curators recommend without reservation, and the block is gone.

*[Subtype classifier]*

> Training a model to predict PAM50 subtype from RNA: Blocked, because the PAM50 label was computed from that same RNA. High accuracy would only show it relearned that rule.

*[Hormone therapy, optional: skip it if you're running long]*

> Hormone therapy response: Blocked. The release doesn't record which tumors got hormone therapy, or any response to it.

### 2:20 Review and sign-off (30 s) · screen: the Review and sign-off page

> No fix is applied on its own. A person approves, rejects, or asks for more evidence on every proposed fix, and a rejection needs a reason. Sign-off writes a signed record in the organizers' shared format. And if a file is damaged or missing, the tool refuses with Insufficient Evidence instead of guessing.

### 2:50 Close (10 s)

> We tested it on 20 releases with answer keys written first: 20 of 20 pass, in about a second each. Hand us the envelope, plant your own errors, or ask your own research question.

**If you run over 3:00:** skip the optional hormone therapy click. Next, shorten the close to "20 of 20 pass. Hand us the envelope."

## Q&A: the sealed envelope

1. The judge gives a number and four words. Aravind types:

   ```bash
   python -m tower envelope <number> <word1> <word2> <word3> <word4>
   ```

2. Read three things aloud:
   - the verdict line
   - each finding: its kind, how severe, how many samples, and which analysis it touches
   - the `valid` line (the organizers' validator passed) and the total time
3. Refresh the screen. The opened envelope appears in the sidebar's release list; pick it and show the question board on the Overview.
4. **If the command fails:** use the sidebar's "Open a sealed envelope" instead. If that also fails, unseal with the organizers' script, then compare. The opened folder is named E plus two digits (envelope 7 opens as `E07`).

   ```bash
   cd ../oncosys-hackathon-challenge && python envelopes/unseal.py <number> <word1> <word2> <word3> <word4>
   ```

   ```bash
   cd ../identity-crisis-control-tower && python -m tower compare ../oncosys-hackathon-challenge/data/tcga-brca/raw ../oncosys-hackathon-challenge/envelopes/opened/E<two digits>/release --challenge ../oncosys-hackathon-challenge --out out/E<two digits>/findings.json
   ```

## If a judge doubts the results: Fool the Tower

Open the **Fool the Tower** page and let the judge pick errors: how many swaps, copies and changed labels, and in which file. Click **Plant these errors and let the tool look**. The organizers' own generator builds that release (about 8 seconds), the tool looks for the errors without the answer key, and the score appears (for example, found 14 of 14 planted samples, 0 false alarms). **Open planted release … on the Overview** shows its verdicts on every question.

## If a judge gives us a different research question

The Track 1 warm-up says judges may change the question. Open **Ask your own question** in the sidebar, pick the closest kind (survival by subtype, a protein between groups, a prediction model, or response to a treatment), click **Judge this question**, and read the verdict and its first reason aloud. The question joins the board, so you can click back to any earlier one. If it fits no kind, say which data the release has and which kind comes closest.

## Likely judge questions

- **How do you know it's right?** We have 20 of 20 test releases. Thirteen were made with the organizers' own generator and graded against its answer keys. We built the other seven, each with its answer written first (`python scripts/scorecard.py ../oncosys-hackathon-challenge/data/tcga-brca/releases`). And you can check any finding yourself: open "Before and after" under it to see the values move, or the Analyses view on the Evidence page, where the organizers' own script gives the same numbers.
- **What about a change you never planned for?** Any changed value shows up in a fingerprint. If it isn't a swap, a copy or a loss, it's reported as an edit, with every sample named.
- **Why Blocked, not a warning?** Even with perfect files, this data can't support that question. A warning would let someone publish a Luminal A survival result from under three years of follow-up.
- **What's the error budget?** How many worst-case errors of each kind (swaps, wrong labels, copies) the answer survives before its 95% range touches zero, and how many this release made. On the practice envelope: 61 swaps between ER groups, and the release made one.
- **What if I change the question?** Ask it in the sidebar form: the same written rules judge it, with the same sources and next steps.
- **Is AI making these calls?** No. Every verdict comes from a written rule with a cited source, and a person signs off.
- **Clinical use?** No. It's for research only: no diagnosis, no treatment advice, no risk scores.

## Check at Friday's 9 PM dry run

- **PFI is Conditional now.** In its group, 2 samples are redacted, 11 have zero follow-up, and the subtype columns disagree. The script's "the block is gone" line still holds; say Conditional if asked.
- **Nothing pending.** Every check is built, so neither the board nor the Overview mentions unbuilt checks.
- **Hook.** Keep the practice hook. Don't use the duplicate-patient story (TCGA-AN-A0FE and TCGA-AN-A0FG): neither sample is in any analysis, and the fact comes from outside annotations, which the rules ask us not to link.
- **The hospital line.** On the ER-alpha question the hospital mix (0.154 on the practice envelope, over the card's 0.15 limit) is the first reason and the first next step, so the script now says it. It's the bias check the event page asks for. If a judge asks more: requiring protein data changes which hospitals the tumors come from, and the next step is to check the result holds with each large hospital left out.
- **Timing.** Read it aloud twice with a stopwatch.

## Where the claims come from

- Practice numbers (747 protein samples, 12 samples cited, the five lost samples all HER2-enriched, 3.051 to 3.019, the 1.2 percent effect, the 2.835 to 3.179 range, 3.047 without the flagged samples): the tool's own output on the practice envelope.
- Follow-up: median 35.4 months for Luminal A primary tumors, by the reverse Kaplan-Meier method (the median observed time is 32.9 months). Both are under three years.
- Endpoint advice: Liu et al., An Integrated TCGA Pan-Cancer Clinical Data Resource to Drive High-Quality Survival Outcome Analytics, Cell 2018, https://doi.org/10.1016/j.cell.2018.02.052. It recommends PFI and DFI without reservation, suggests caution with overall survival in breast cancer, and says overall survival may suit the basal-like subtype but not Luminal A.
- PAM50 is computed from gene expression: Parker et al., Supervised Risk Predictor of Breast Cancer Based on Intrinsic Subtypes, J Clin Oncol 2009, https://doi.org/10.1200/JCO.2008.18.1370.
