"""Plain-English presentation of frozen evidence (reviewer-facing text only).

Reads the frozen packet dict, never writes it. Explains what each number IS, never what it MEANS.
Rounded values are display-only; section 6 of every packet repeats the exact stored values.
Gap/ratio definitions below were checked arithmetically against the stored numbers (and, for
robustness/integrity, against backend/app/probes/robustness_eval.py and integrity_artifact.py).
"""

# --------------------------------------------------------------------------- form introduction
INTRO = [
    ("Please read first",
     "This form asks you to review 12 short evidence packets (P01-P12) and give your own independent "
     "judgment on each. No AI or technical background is needed: everything you need is explained here and "
     "inside each packet.\n\n"
     "What system is being reviewed? A computer program (a 'classifier') that reads an English online comment "
     "and labels it as either toxic or not toxic. Each packet describes tests run on one such program. The "
     "programs are not named.\n\n"
     "What is TrustLens? TrustLens is a software tool that automatically runs tests on AI systems like this "
     "one and measures how trustworthy they are in five areas (listed below). The packets contain raw "
     "measurements from such tests. The tool's own conclusions are deliberately NOT shown, so that your "
     "judgment is independent.\n\n"
     "What are you asked to judge? For each packet you answer the same five questions: (1) is the evidence "
     "enough to make a judgment, (2) does it show a meaningful risk, (3) which of the five areas does it "
     "concern, (4) how serious would the consequences be, and (5) a short reason in your own words."),
    ("Ground rules",
     "- Everything you need is provided in the packet. Judge only the evidence shown.\n"
     "- Do not search for, or try to identify, the original program or model.\n"
     "- Work alone. Do not discuss packets or answers with anyone until all reviewers have submitted.\n"
     "- There are no right or wrong answers. Where the evidence is unclear or missing, say so "
     "(question 1 and your rationale).\n"
     "- Square-bracket tokens such as [LIBRARY-NAME] or [DATASET-A] inside quoted documentation are "
     "placeholders for redacted names. Ignore them.\n"
     "- Numbers in the explanations are rounded for readability. Each packet ends with the exact stored "
     "values."),
    ("The five areas (FRIES)",
     "- Fairness: whether the program performs similarly for different groups of comments.\n"
     "- Robustness: whether its performance holds up when the input text is changed slightly.\n"
     "- Integrity: whether the files that make up the program are the expected ones, compared with a "
     "reference.\n"
     "- Explainability: what the documentation published with the program tells users about what it is for, "
     "its limits, how it was trained and tested, and ethical considerations. (It is not about explanations "
     "of individual predictions.)\n"
     "- Safety: how the program behaves on potentially harmful, severe content.\n\n"
     "Each packet starts with a short note on what kind of evidence it contains."),
    ("Common terms",
     "- Toxic / not toxic: toxic means abusive, hateful or disrespectful language, as judged by the human "
     "labelers of the comments; not toxic is everything else. 'Positive' means toxic, 'negative' means not "
     "toxic.\n"
     "- Accuracy: the share of comments the program labelled correctly.\n"
     "- TPR (true positive rate): of the comments that really are toxic, the share the program correctly "
     "flagged as toxic.\n"
     "- FPR (false positive rate): of the comments that really are not toxic, the share the program wrongly "
     "flagged as toxic.\n"
     "- Accuracy drop: accuracy on the original comments minus accuracy after small changes were made to "
     "them.\n"
     "- Percentage points: the unit for the difference between two percentages (20% vs 30% is a gap of 10 "
     "percentage points).\n"
     "- Confidence interval (95%): the range of values that is plausible for the true figure, given that "
     "the figure was estimated from a sample. A wider range means more uncertainty.\n"
     "- null / not reported: no value was stored for that measurement.\n"
     "- Severity (question 4): how serious the consequences would be if the problem you see were real and "
     "left unaddressed. 1 = catastrophic, 5 = moderate, 9 = negligible. It is about consequences, not about "
     "how sure you are that there is a problem. Choose 'N/A - no risk identified' if you see no risk."),
]

EXPLAINER = {
    "FAIRNESS": "The evidence in this packet compares how the classifier performs for two groups of comments. "
                "The differences between the groups are reported as numbers. You decide what, if anything, "
                "they mean.",
    "ROBUSTNESS": "The evidence in this packet examines how the classifier's performance changes after small "
                  "changes are made to the input text. You decide what, if anything, the changes mean.",
    "INTEGRITY": "The evidence in this packet checks whether the files used by the classifier match the "
                 "expected reference files. You decide what, if anything, the result means.",
    "EXPLAINABILITY": "The evidence in this packet concerns what the model's documentation (its 'model card') "
                      "tells users about its intended use, limitations, training, evaluation and ethical "
                      "considerations. It does NOT assess explanations of individual predictions. You decide "
                      "what, if anything, the documentation shows.",
    "SAFETY": "The evidence in this packet examines how the classifier behaves on potentially harmful, severe "
              "content, including how often it misses such content. You decide what, if anything, the numbers "
              "mean.",
}


# --------------------------------------------------------------------------- helpers
def pct(x):
    return "not reported" if x is None else f"{x * 100:.1f}%"


def pts(x):  # a difference between two rates, in percentage points
    return "not reported" if x is None else f"{x * 100:.1f} percentage points"


def ci(pair, unit=" percentage points"):
    if pair is None:
        return "no interval reported"
    lo, hi = pair[0] * 100, pair[1] * 100
    return f"{lo:.1f}% to {hi:.1f}%" if unit == "%" else f"{lo:.1f} to {hi:.1f}{unit}"


def table(rows, header):
    w = max(len(r[0]) for r in rows + [header])
    return "\n".join("  " + f"{r[0]:<{w}}" + "".join(f"  | {c:>10}" for c in r[1:]) for r in [header] + rows)


def sections(s1, s2, s3, s4, s5, s6):
    return [("1. What was tested?", s1), ("2. What was measured?", s2), ("3. What each measure means", s3),
            ("4. The results", s4), ("5. Uncertainty", s5), ("6. Technical details (exact stored values)", s6)]


# --------------------------------------------------------------------------- FAIRNESS
def fairness(ev, raw):
    g0, g1 = ev["groups"]["0"], ev["groups"]["1"]
    s1 = (f"A computer program (a classifier) reads English online comments and labels each one as toxic or not "
          f"toxic. Here it was run on {ev['n_evaluated']:,} comments whose correct label is already known.\n\n"
          f"The comments are split into two groups by whether the comment references an identity:\n"
          f"  - Group 0: comments that do NOT reference an identity ({g0['n']:,} comments)\n"
          f"  - Group 1: comments that DO reference an identity ({g1['n']:,} comments)\n\n"
          f"'Positive' means 'toxic'. 'Negative' means 'not toxic'.")
    s2 = ("For each group separately, and then as differences between the two groups, the evidence reports how "
          "often the program flags comments as toxic and how often it is right or wrong about them. It also "
          "reports how uncertain each difference is.")
    s3 = ("Per-group measures (each is a percentage of that group's comments):\n"
          "  - Actually toxic: the share of the group's comments whose correct label is toxic.\n"
          "  - Flagged as toxic: the share of the group's comments the program labelled toxic.\n"
          "  - TPR (true positive rate): of the comments that really are toxic, the share the program "
          "correctly flagged.\n"
          "  - FPR (false positive rate): of the comments that really are not toxic, the share the program "
          "wrongly flagged as toxic.\n"
          "  - F1: a single score from 0 to 100 that combines two things: how many flagged comments really "
          "were toxic (precision) and how many toxic comments got flagged (recall).\n\n"
          "Between-group differences (always the larger group value minus the smaller; 0 = identical):\n"
          "  - Demographic parity difference: the gap between the groups in the share flagged as toxic.\n"
          "  - Equal opportunity difference: the gap between the groups in TPR.\n"
          "  - FPR gap: the gap between the groups in FPR.\n"
          "  - Equalized odds difference: the larger of the TPR gap and the FPR gap.\n"
          "  - F1 spread: the gap between the two groups' F1 scores.\n"
          "  - Label rate gap: the gap between the groups in how many comments are actually toxic (this is "
          "about the comments, not the program).")
    rows = [("Number of comments", f"{g0['n']:,}", f"{g1['n']:,}"),
            ("Actually toxic (count)", f"{g0['positive_labels']:,}", f"{g1['positive_labels']:,}"),
            ("Actually toxic (share)", pct(g0["positive_label_rate"]), pct(g1["positive_label_rate"])),
            ("Flagged as toxic (share)", pct(g0["predicted_positive_rate"]), pct(g1["predicted_positive_rate"])),
            ("TPR", pct(g0["tpr"]), pct(g1["tpr"])),
            ("FPR", pct(g0["fpr"]), pct(g1["fpr"])),
            ("F1 (0-100)", f"{g0['f1'] * 100:.1f}", f"{g1['f1'] * 100:.1f}")]
    s4 = (f"Per group:\n{table(rows, ('Measure', 'Group 0', 'Group 1'))}\n\nDifferences between the groups:\n"
          f"  Demographic parity difference: {pts(ev['demographic_parity_difference'])}\n"
          f"  Equal opportunity difference (TPR gap): {pts(ev['equal_opportunity_difference'])}\n"
          f"  FPR gap: {pts(ev['fpr_gap'])}\n"
          f"  Equalized odds difference: {pts(ev['equalized_odds_difference'])}\n"
          f"  F1 spread: {pts(ev['subgroup_f1_spread'])}\n"
          f"  Label rate gap: {pts(ev['label_rate_gap'])}")
    s5 = ("Every difference above is an estimate from a sample of comments, so it is not exact. A 95% confidence "
          "interval is the range of values that is plausible for the true difference given that sampling "
          "uncertainty. A wider range means a less certain estimate. The ranges were found by re-sampling the "
          f"comments {ev['ci_method'].split('B = ')[1]} times ({ev['ci_method']}).\n\n"
          f"  Demographic parity difference: {ci(ev['demographic_parity_difference_ci95'])}\n"
          f"  Equal opportunity difference: {ci(ev['equal_opportunity_difference_ci95'])}\n"
          f"  Equalized odds difference: {ci(ev['equalized_odds_difference_ci95'])}\n"
          f"  F1 spread: {ci(ev['subgroup_f1_spread_ci95'])}\n"
          "  (No interval was reported for the FPR gap or the label rate gap.)")
    s6 = (f"Original description of the test set: {ev['evaluation_set']}\n"
          f"The analysis was set up to require at least {ev['minimum_group_size_configured']} comments per "
          f"group.\nExact stored values:\n{raw}")
    return sections(s1, s2, s3, s4, s5, s6)


# --------------------------------------------------------------------------- ROBUSTNESS
def robustness(ev, raw):
    s1 = ("A computer program (a classifier) labels English online comments as toxic or not toxic. It was "
          "tested twice on the same comments: once on the original text, and once after small random changes "
          f"were made to the text ({ev['perturbation']}).\n\n"
          f"Before the test: {ev['input_preprocessing']}.\n"
          f"Comments used: {ev['n_evaluated']:,}.")
    s2 = ("How often the program labelled comments correctly on the original text versus the changed text, how "
          "much that differs, and how uncertain the difference is. Also how many comments could actually be "
          "changed.")
    s3 = ("  - Clean accuracy: the share of comments labelled correctly on the original text.\n"
          "  - Robust accuracy: the share labelled correctly after the text was changed.\n"
          "  - Accuracy drop: clean accuracy minus robust accuracy, in percentage points.\n"
          "  - Robust accuracy as a share of clean accuracy: robust accuracy divided by clean accuracy "
          "(stored as 'relative degradation').\n"
          "  - Flip rate (stored as 'attack success rate'): the share of ALL comments the program labelled "
          "correctly before the change but incorrectly after it.\n"
          "  - Perturbation coverage: the share of comments the random changes were able to alter.\n"
          "  - Rows not perturbable: the number of comments the changes could not alter.")
    drop_ci = ev["accuracy_drop_ci95"]
    s4 = (f"  Comments used: {ev['n_evaluated']:,}\n"
          f"  Perturbation coverage: {pct(ev['perturbation_coverage'])}\n"
          f"  Rows not perturbable: {ev['rows_not_perturbable']}\n"
          f"  Clean accuracy: {pct(ev['clean_accuracy'])}\n"
          f"  Robust accuracy: {pct(ev['robust_accuracy'])}\n"
          f"  Accuracy drop: {pts(ev['accuracy_drop'])}\n"
          f"  Robust accuracy as a share of clean accuracy: {pct(ev['relative_degradation'])}\n"
          f"  Flip rate (attack success rate): {pct(ev['attack_success_rate'])}")
    if any(ev[k] is None for k in ("clean_accuracy", "robust_accuracy", "accuracy_drop")):
        s4 += "\n\n'not reported' means no value was stored for that measurement."
    s5 = ("Results are estimated from a sample of comments, so they are not exact. A 95% confidence interval is "
          "the range of values that is plausible for the true figure; a wider range means more uncertainty.\n\n"
          f"  Accuracy drop: {ci(drop_ci)}")
    s6 = f"Exact stored values:\n{raw}"
    return sections(s1, s2, s3, s4, s5, s6)


# --------------------------------------------------------------------------- SAFETY
def safety(ev, raw):
    ref = ev["reference_model_same_data"]
    s1 = ("A computer program (a classifier) labels English online comments as toxic or not toxic. It was run on "
          f"3,000 comments whose correct label is already known. {ev['severe_n']} of them are toxic comments "
          "that the human labelers marked as SEVERELY toxic; the evidence looks at how often those are missed.\n\n"
          "A second, published toxicity classifier was run on the same 3,000 comments, for comparison.")
    s2 = ("How often the program fails to flag toxic comments, with extra attention on severely toxic ones; how "
          "much of the toxic content it detects overall; how often it wrongly flags harmless comments; and the "
          "same 'missed' figure for the comparison classifier.")
    s3 = ("  - FNR (false negative rate): of the comments that really are toxic, the share the program missed "
          "(labelled not toxic).\n"
          "  - Severe FNR: the same, counted only over the severely toxic comments.\n"
          "  - Overall FNR: the same, counted over all toxic comments.\n"
          "  - FNR ratio: severe FNR divided by overall FNR.\n"
          "  - Harmful recall: the share of all toxic comments the program detected (100% minus overall FNR; "
          "the same thing as TPR).\n"
          "  - Benign FPR: the share of comments that really are not toxic that the program wrongly flagged "
          "as toxic (the FPR).\n"
          "  - Comparison classifier: a published toxicity classifier measured on the same comments. It is "
          "shown only for reference.")
    s4 = (f"  Severely toxic comments: {ev['severe_n']}\n"
          f"  Severe FNR: {pct(ev['severe_fnr'])}\n"
          f"  Overall FNR: {pct(ev['overall_fnr'])}\n"
          f"  FNR ratio (severe / overall): {ev['fnr_ratio']:.2f}\n"
          f"  Harmful recall: {pct(ev['harmful_recall'])}\n"
          f"  Benign FPR: {pct(ev['benign_fpr'])}\n\n"
          f"  Comparison classifier, same comments:\n"
          f"    Severe FNR: {pct(ref['severe_fnr'])}")
    s5 = ("The severe FNR is estimated from a sample, so it is not exact. A 95% confidence interval is the range "
          "of values that is plausible for the true figure; a wider range means more uncertainty.\n\n"
          f"  Severe FNR: {ci(ev['severe_fnr_ci95'], '%')}\n"
          f"  Comparison classifier severe FNR: {ci(ref['severe_fnr_ci95'], '%')}\n"
          "  (No interval was reported for the other measures.)")
    s6 = f"Original description of the test set: {ev['evaluation_set']}\nExact stored values:\n{raw}"
    return sections(s1, s2, s3, s4, s5, s6)


# --------------------------------------------------------------------------- INTEGRITY
def integrity(ev, raw):
    av = ev["artifact_verification"]
    man = av["manifest"]

    def short(h):
        return "(none)" if h is None else h[:12] + "..."

    state = {"match": "identical", "changed": "differs"}
    rows = [(f["name"], state.get(f["state"], f["state"]), short(f["sha256"]), short(f["expected_sha256"]))
            for f in av["files"]]
    w = max(len(r[0]) for r in rows + [("File",)])
    tab = "\n".join(f"  {r[0]:<{w}} | {r[1]:<9} | {r[2]:<15} | {r[3]}" for r in
                    [("File", "Result", "Fingerprint", "Expected")] + rows)
    s1 = ("A computer program (a classifier) labels English online comments as toxic or not toxic. It is stored "
          "as a small set of files (settings, vocabulary, and the learned numbers called 'weights'). This test "
          "checks whether the files that were actually used are identical to the files on a reference list "
          f"recorded from a known-good copy. Stored description of the reference list: '{ev['reference_manifest']}'.")
    s2 = ("For each file, a 'fingerprint' was computed and compared with the fingerprint on the reference list. "
          "No sample of comments is involved: this is an exact comparison.")
    s3 = ("  - Fingerprint (SHA-256): a 64-character code computed from a file's exact contents. Identical files "
          "always give the same code; changing even one byte gives a completely different code.\n"
          "  - Reference list (manifest): the list of file names and their expected fingerprints.\n"
          "  - Overall status:\n"
          "      VERIFIED = every expected file was present and its fingerprint matched the reference list.\n"
          "      MISMATCH = at least one file's fingerprint differs from the reference list (or an unlisted "
          "weight file was present).\n"
          "      Other possible statuses: INCOMPLETE (an expected file was absent), UNPINNED (no reference "
          "list to compare with), UNSUPPORTED / UNVERIFIABLE (the check could not be run).\n"
          "  - File result: 'identical' = fingerprint matches the reference; 'differs' = it does not.\n"
          "  - Format 'safetensors': a common file format for storing the learned numbers.\n"
          "  - Sharded: whether the weights are split across several files.")
    s4 = (f"  Check performed: {'yes' if av['performed'] else 'no'}\n"
          f"  Overall status: {av['status']}\n"
          f"  Weight file format: {av['format']}; sharded: {'yes' if av['sharded'] else 'no'}\n"
          f"  Reference list: {man['n_files']} files, source '{man['source']}'\n"
          f"  Files with a differing fingerprint: {len(av['mismatches'])}\n\n"
          f"Per file (first 12 characters of each fingerprint):\n{tab}\n\n"
          f"Other stored details: model revision: {ev['model_revision']}; license named in the model card: "
          f"{ev['card_license']}.")
    s5 = ("Not applicable in the usual sense: fingerprints are compared exactly, so there is no sampling "
          "uncertainty and no confidence interval was reported.")
    s6 = f"Full fingerprints and all other stored values:\n{raw}"
    return sections(s1, s2, s3, s4, s5, s6)


# --------------------------------------------------------------------------- EXPLAINABILITY
TOPICS = [("intended_use", "Intended use (what the model is meant for)"),
          ("limitations", "Limitations"), ("training_data", "Training data"),
          ("evaluation", "Evaluation (how it was tested)"), ("ethical_considerations", "Ethical considerations")]


def explainability(ev, raw):
    det = ev["automated_section_detection"]
    found = sum(bool(det[k]) for k, _ in TOPICS)
    s1 = ("A computer program (a classifier) labels English online comments as toxic or not toxic. Programs like "
          "this usually come with a written description called a model card. This packet is about that "
          "document: the full text is reproduced further below, exactly as stored (apart from redacted "
          "names).\n\nAn automated, keyword-based check was also run on the text.")
    s2 = ("Which of five standard documentation topics the automated check found in the text, and how long the "
          "document is. The check does not read the text for meaning.")
    s3 = ("  - Model card: the document published with the program to tell users about it.\n"
          "  - Automated section detection: a keyword/heading search for five topics: intended use, "
          "limitations, training data, evaluation, and ethical considerations. 'Found' means the search "
          "located matching words or headings. It does NOT judge whether the content is good, complete or "
          "true; you may judge that yourself.\n"
          "  - Coverage: the number of the five topics found, divided by five.\n"
          "  - Characters: the length of the document.")
    rows = [(label, "found" if det[k] else "not found") for k, label in TOPICS]
    w = max(len(r[0]) for r in rows)
    s4 = ("Automated check:\n" + "\n".join(f"  {a:<{w}} | {b}" for a, b in rows) +
          f"\n\n  Topics found: {found} of 5 (coverage {pct(ev['coverage_ratio'])})\n"
          f"  Document length: {ev['card_chars']:,} characters")
    s5 = ("Not applicable in the usual sense: this evidence is a document and a keyword search, not an estimate "
          "from a sample, so no confidence interval was reported.")
    s6 = f"Exact stored values (the full card text is shown in the next block):\n{raw}"
    return sections(s1, s2, s3, s4, s5, s6)


RENDER = {"FAIRNESS": fairness, "ROBUSTNESS": robustness, "SAFETY": safety, "INTEGRITY": integrity,
          "EXPLAINABILITY": explainability}
