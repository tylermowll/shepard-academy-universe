# Local evaluation intake

The maintainer supplied six images downloaded from the internet on 2026-09-07.
Original URLs, authors and redistribution licenses have not been supplied. The
unaltered files are in ignored `internet-examples/`; they are not covered by this
repository's MIT fixture license and are not part of CI or the public dataset.
No application/provider inference was performed. The following is a visual intake
assessment, not a model-quality result or an exact transcription ground truth.

| Original file                            | Size    | Useful evaluation                                                                        | Limitations                                                                      |
| ---------------------------------------- | ------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `621fc3d35d25032f1d530059_messy.gif`     | 200×180 | Tiny, rotated annotations and scattered geometry work; model should flag unreadable text | Very low resolution; GIF is intentionally unsupported by the upload API          |
| `621fc3d35d25037975530058_mess_neat.gif` | 324×199 | Two layouts of algebraic work, crossed-out expressions and symbol ambiguity              | Low resolution; unsupported GIF; not a single app-assigned answer                |
| `621fc3d35d2503d5af53004c_bad1.gif`      | 492×771 | Cursive mathematical prose, modular arithmetic, heavily crossed-out lines                | Unsupported GIF; needs independently reviewed reading/feedback expectations      |
| `bad-scratch-work.png`                   | 491×626 | Dense scratch work, multiple columns, matrices, fractions and crossed-out answers        | Requires selecting one problem; full page has no single trustworthy final answer |
| `images.jpeg`                            | 280×560 | Cropped combinatorial derivation with stacked fractions and binomial notation            | Low resolution, clipped right edge; useful missing-context/rejection case        |
| `scrappaper.png`                         | 640×483 | Faint multi-directional graph-theory notes, diagrams and background show-through         | Good ambiguity/retake case; not an answer-key grading fixture                    |

Use the PNG/JPEG examples for local manual capture/preview and ambiguity review.
The three original GIFs are useful format-rejection cases. If creating PNG copies
for a separately authorized vision evaluation, preserve originals and document
the chosen frame and conversion. Do not silently broaden accepted upload types.

Local decoder check on 2026-09-07: `math_tutor.adapters.images.normalize` accepted
all three PNG/JPEG files and returned metadata-free PNGs at their original
dimensions; it rejected all three valid GIFs as unsupported. Nothing was sent to
a model or saved as a learner submission. A newly authored in-memory GIF now
tests the same rejection rule in `apps/api/tests/unit/test_images.py`, without
depending on these unlicensed downloads.

To promote a candidate into the public suite, record its exact source URL, author,
license/permission, file hash, selected problem/crop, and independently reviewed
expected transcription (including intentionally unreadable regions). Until then,
use these as references for creating original synthetic cases. Benchmark the
actual phone workflow with newly authored handwritten work across subjects as well;
these web images do not establish real iPhone camera performance.

T25 removes the earlier fixed-math tutoring restriction. These examples can
inform tests of reading, organization advice, and conceptual guidance, but they
still lack redistribution permission and independently reviewed expected results.
An uncertain reading should request clearer work without an approval gate.
