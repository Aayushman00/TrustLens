/**
 * Creates the L10 human-review Google Form (12 anonymised packets, fixed order)
 * plus a linked response Sheet. GENERATED from template by build_form.py.
 * Run createL10Form() once from script.google.com; see the log for the URLs.
 * This script never submits responses.
 */
const INTRO = /*INTRO_JSON*/;
const PACKETS = /*PACKETS_JSON*/;

const DIMS = ['FAIRNESS', 'ROBUSTNESS', 'INTEGRITY', 'EXPLAINABILITY', 'SAFETY', 'UNCERTAIN'];
const SEVERITY = ['1 = catastrophic', '2', '3', '4', '5 = moderate', '6', '7', '8', '9 = negligible',
  'N/A — no risk identified'];
const TRI = ['YES', 'NO', 'UNCERTAIN'];

function createL10Form() {
  const form = FormApp.create('L10 Evidence Review');
  form.setDescription(
    'You will review 12 anonymised evidence packets (P01-P12). Judge what the evidence supports. ' +
    'No automated verdict is shown, on purpose. Work alone; do not discuss packets until everyone has submitted. ' +
    'Use only what is shown on the page. Answers cannot be edited after submission.')
    .setCollectEmail(false)
    .setLimitOneResponsePerUser(false)
    .setAllowResponseEdits(false)
    .setProgressBar(true)
    .setShuffleQuestions(false)
    .setConfirmationMessage('Thank you. Your responses were recorded.');

  INTRO.forEach(function (b) {
    form.addSectionHeaderItem().setTitle(b.h).setHelpText(b.t);
  });

  form.addTextItem()
    .setTitle('Reviewer code')
    .setHelpText('The code the organiser gave you (e.g. R1). Do not enter your name or email.')
    .setValidation(FormApp.createTextValidation().requireTextMatchesPattern('^[A-Za-z0-9_-]{1,12}$').build())
    .setRequired(true);

  PACKETS.forEach(function (p) {
    form.addPageBreakItem()
      .setTitle('Packet ' + p.id)
      .setHelpText('Task: ' + p.task);
    p.blocks.forEach(function (b) {
      form.addSectionHeaderItem().setTitle(p.id + ' - ' + b.h).setHelpText(b.t);
    });
    // Titles carry the packet id so Sheet columns are unambiguous.
    form.addMultipleChoiceItem().setTitle(p.id + ' Q1. Is the evidence sufficient to make your judgment?')
      .setChoiceValues(TRI).setRequired(true);
    form.addMultipleChoiceItem().setTitle(p.id + ' Q2. Is there evidence of a meaningful risk?')
      .setChoiceValues(TRI).setRequired(true);
    form.addMultipleChoiceItem().setTitle(p.id + ' Q3. Which FRIES dimension does the evidence concern?')
      .setChoiceValues(DIMS).setRequired(true);
    form.addListItem().setTitle(p.id + ' Q4. Severity')
      .setHelpText('Consequence if the problem went unaddressed: 1 = catastrophic ... 9 = negligible. ' +
                   'Choose N/A only if you see no risk.')
      .setChoiceValues(SEVERITY).setRequired(true);
    form.addParagraphTextItem().setTitle(p.id + ' Q5. Brief rationale')
      .setHelpText('1-3 sentences citing the specific numbers or text that drove your answers.')
      .setRequired(true);
  });

  const ss = SpreadsheetApp.create('L10 Evidence Review - responses');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  Logger.log('Edit URL:      ' + form.getEditUrl());
  Logger.log('Reviewer URL:  ' + form.getPublishedUrl());
  Logger.log('Response sheet: ' + ss.getUrl());
}
