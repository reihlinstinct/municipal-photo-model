# Private municipal photo review

This is a local review tool, not a hosted labeling service. It makes no external
requests, runs no model and never uploads anything. The Hebrew RTL interface fits
phones; images are loaded one at a time. Code is public; real photos, candidates,
state, exports and screenshots must stay outside this checkout and remain private.

## Prepare the private input

Use the pilot's private `manifest.candidates.json`, which already contains the
packaged image paths, hashes and groups. The tool requires a nonempty JSON array. Each row has:

- Optional `local_source_id`: source report identifier. The uploaded pilot omits
  this field deliberately; it is not required.
- `candidate_labels`: a list containing only the three supported class keys.
- `label_state`: all three class keys, each `unknown`. Proposals are not truth.
- `group_id`: verified whole-location/event group, a nonempty string.
- `review_status`: nonempty unreviewed status, normally
  `needs_visual_and_event_review` or `held_missing_group_data`.
- `image`: relative JPEG/PNG path inside the private dataset root.
- `image_sha256`: SHA-256 of those exact bytes.
- Existing candidate fields such as `upload_approved`, proposed boxes and source
  metadata are preserved. They are not automatically copied into approved labels.
- Optional `municipal_category` or `city_label`: the municipality's original classification, not
  a model class. Add source event/category context as extra fields where available.
  The UI shows the entire row as inert text so the reviewer can inspect evidence.

The pilot's `CONTENTS.json` is a summary, not a candidate manifest. It is not
needed by this tool. Select `manifest.candidates.json` instead. If that file is
missing, recover the private packaging/source index first.
Do not invent image-to-report mappings, location groups, municipal classifications
or approvals from filenames. A `held_missing_group_data` row cannot be approved;
repair its source data before starting a fresh review, or exclude it explicitly.

The private `plate_text_candidate` field is removed before any UI/API output or
export. It is never shown, logged, or copied into visible plate text. The reviewer
transcribes the observed plate independently. Additional pilot metadata is
preserved without treating mapping flags or vehicle candidates as reviewed truth.

The loader checks containment (including symlinks), hashes, unique image paths,
orientation and basic candidate schema. Identical images and repeated source
events must share one group. The loader cannot prove location grouping from
images alone: the preparation step must preserve the original source grouping.
Photos with non-identity EXIF orientation are rejected; prepare pixel-oriented
copies and compute their hashes before review, never rotate reviewed bytes.

## Run on a computer

Python 3.11+ and Pillow are required (the repo test requirements pin Pillow).
From the code checkout:

```sh
python -m pip install -r requirements-test.txt
python scripts/review_server.py \
  --root /private/pilot \
  --candidates /private/pilot-candidates.json \
  --work /private/pilot-review
```

Open the private local address printed in the terminal, including its fragment.
It contains a random session token; do not share it. The default binds only to the
same computer, not the LAN or internet. Stopping/restarting changes the token but
preserves drafts in `--work`. Keep only one server process per work directory.
Same-server tabs have optimistic revision checks; a stale tab cannot overwrite
newer work. Back up the private work directory periodically, with the same privacy
as the images. An export is invalidated when any later edit is saved.

### iPhone Safari

`127.0.0.1` on a phone means the phone, not the computer. A plain local HTML file
cannot provide this server's private image/state access. No phone hosting is
created by this change.

For phone use, run the same server on a computer reachable on a private network,
with a certificate trusted by the phone for that computer's hostname/IP:

```sh
python scripts/review_server.py \
  --root /private/pilot --candidates /private/pilot-candidates.json \
  --work /private/pilot-review --bind PRIVATE_INTERFACE_IP \
  --cert /private/host-cert.pem --key /private/host-key.pem
```

Replace the placeholders with an existing private interface and certificate.
Non-loopback binding is refused without TLS. Use a private interface, a firewall,
and a trusted device/network; do not expose a public interface, port-forward, use
an unauthenticated tunnel or upload photos to a static site. The session token is
required on every image/data/state API call, is sent in the Authorization header,
and is removed from browser history after load. There are no third-party assets,
analytics, CORS grants or persistent image caches. App assets alone contain no data.

If no existing private phone-reachable TLS route is available, choose a private
host/certificate setup before claiming the phone is ready. The desktop route is
usable without that decision and costs nothing. iPhone Safari still needs an
actual-device check; automated WebKit is a compatibility check, not an iPhone.

## Review

1. Inspect the photo and the original report event/category evidence. The source
   panel shows proposals and metadata, not proof of human review.
2. Tap **mark vehicle** then two opposite corners of the actual target vehicle.
   Mark the plate the same way. Increase the zoom slider and scroll the image
   before marking a small plate. Numeric coordinate fields allow corrections.
3. Confirm the exact municipal classification. For each baseline class choose
   present or absent. Unknown is allowed in drafts, never an approved export.
4. Confirm visual target selection and original-event review separately. These
   boxes must reflect real review, not be checked just to unlock export.
5. For a readable plate, mark its box and enter only observed text. For a visible
   but unreadable plate, keep the box and leave the text blank. For no visible
   plate, clear both box and text. Do not infer or guess plate text.
6. Assign a group split explicitly; every retained image in a group must share
   train, val or test. Keep whole-location/event groups intact. No automatic
   random split or group propagation happens. Export checks leakage and checks
   positives and negatives for each class in train, as the worker does.
7. Enter the reviewer's name. Save a draft, approve the image, or exclude it with
   a reason. Navigate after saving. Unsaved changes prompt before navigation.

Box convention: **`[x1, y1, x2, y2]` in original-image pixels**, origin top-left,
with `0 <= x1 < x2 <= width` and `0 <= y1 < y2 <= height`. These are continuous
pixel edges, not normalized coordinates or width/height. Plate boxes must be
inside the selected target vehicle box. The worker currently only checks that a
target box is non-null; this tool adds the missing geometric validation without
changing or bypassing that worker gate.

## Export and return to Kaggle

Export is blocked until every image is approved or explicitly excluded, every
included row is fully reviewed, groups do not leak, all three splits exist, and
training has positives and negatives for each baseline class. Excluded rows do
not enter the training manifest; their decisions/reasons stay in the audit.
The original candidates and image bytes are never changed.

Successful export writes `manifest.reviewed.json` and `review-audit.json` in the
private work directory, and offers a JSON download. On Safari, use the Files
save/download action if prompted. The computer-side copy is authoritative if a
phone download is awkward. Draft saves go to `review-state.json` atomically.
Changing any saved review invalidates the previous local manifest export.

Only after the human review has actually happened:

1. Retain the original source manifest and private audit as provenance. Copy the
   newest exported `manifest.reviewed.json` into a **private staging copy** of the
   same pilot dataset root. Preserve the exact image relative paths and bytes.
2. Recheck every image hash and group split. Update the private `CONTENTS.json`
   counts honestly from the reviewed export, including excluded images. Do not
   mark the dataset training-ready if any required review check remains blocked.
3. Have the existing authorized Kaggle workflow create a new version of the same
   **private** dataset, with the reviewed manifest included. Reconfirm that the
   destination is private. This review tool does not execute that upload and a
   human review does not itself authorize publication or a new training run.
4. Verify the new version contains the manifest and the same images, then stage
   a separately authorized bounded training run. Keep all existing worker gates,
   safety caps and group checks intact. A valid review manifest is necessary, not
   a promise that training will succeed or achieve useful accuracy.

The current ResNet baseline trains only `sidewalk_parking`, `red_white`, and
`crosswalk_obstruction`. It does **not** train plate detection/OCR, consume target
crops, or learn the municipality's full classification. Plate annotations,
municipal categories, reviewer/timestamps, notes and `box_format` are preserved as
extra metadata for future reviewed training work. No claim of plate training is
made. `upload_approved` is false on export: review is not a disclosure grant.

## Verification

Run the repository tests and privacy checks. All fixtures are generated at runtime
in a temporary directory; no real photo, plate, source ID or reviewed manifest is
committed. The tests cover resume, stale writes, gates, geometry, plate states,
hashes, path/symlink containment, grouped splits, exclusions, and API auth.

Optional repeatable browser checks (not required by CI): install Playwright in a
separate test environment with Chromium available as `/usr/bin/google-chrome`,
then run `python tests/review_browser_check.py`. It checks 320px, 390px and desktop
layouts, two-corner annotation, approval, resume, edits and downloaded manifest
export using generated images only. It writes screenshots/output to a temporary
folder outside the checkout. No browser dependencies are added to production.
