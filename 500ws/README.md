# 500 Women Scientists Bern-Fribourg

Static website prototype: https://glecko.xyz/500ws/

The source lives in the `500ws/` folder of `glebo309/glebo309.github.io`. The existing association domain and Wix site are unchanged. Prototype pages ask search engines not to index them.

## Team editing

The unlisted editor entry is https://glecko.xyz/500ws/login/. It is absent from public navigation and asks search engines not to index it. An unlisted address is a convenience; actual access control is provided by Pages CMS and GitHub.

The owner must first sign into https://app.pagescms.org/, connect only the `glebo309/glebo309.github.io` repository, select its `main` branch, and invite editors by email. Invited collaborators can edit the configured content and media without a GitHub account. The repository-wide GitHub App grant is broader than the `500ws/` content shown in the editor; keep installation access limited to this selected repository and revoke it when migrating to the association's own repository.

No passwords, personal access tokens or OAuth secrets belong in these website files. Do not share the owner's GitHub login. Only public website content should be entered into the editor; it is stored in a public repository.

Once connected, editors can select Website pages, Community, Events, Stories, or News & letters, make changes using labelled fields and a formatted-text editor, upload photos, and save. The GitHub workflow rebuilds the pages and requests publication. Changes normally take a few minutes. The GitHub Actions log shows any failed publication.

The connection and collaborator invitations require the owner's setup. No invitation has been sent. Until then, the prototype can be viewed and shared, but board members cannot save edits.

The configuration is `.pages.yml` at the personal repository root, with paths scoped to `500ws/`. This download contains a matching copy as a deployment reference. `settings.content.merge` preserves historical fields that are not exposed in the editor.

Official editor documentation: https://pagescms.org/docs/quick-start/ and https://pagescms.org/docs/configuration/collaborators/

## Source and local preview

- `content/site.json`: homepage introduction, main image, contact email, about copy, resources, reading and archive material.
- `content/members`, `content/posts`, `content/events`, `content/news`: one JSON file per editable entry.
- `build.py`: shared page templates and generated-page assembly.
- `content_tools.py`: content loading, portable media paths and safe article markup.
- `styles.css` and `site.js`: presentation, responsive header, navigation, search and event classification.
- `assets/`: local images, fonts and PDFs.

Run `python3 build.py` after editing source content. Run `python3 -m unittest discover -s . -p test_build.py -v` to check publishing behavior. These use Python's standard library. Run `python3 -m http.server 8765 --bind 127.0.0.1` for a local preview.

Generated HTML should not be edited directly because the next build replaces it. Shared layout, navigation labels, FAQ wording and some homepage section labels still live in the template. Content changes use the editor; structural redesigns require a code change.

## Migration coverage

Captured from the public Wix website on 7 November 2026:

- 25 current member biographies, with roles and profile links.
- 22 blog stories with their complete text and article images.
- 22 dated events and nine news items.
- March 2023 SERI letter and the university accreditation initiative.
- 16 newsletter PDFs: 15 issues plus a distinct January 2022 version.
- Seven additional campaign and event documents.
- Original About, Swiss association, resource and reading descriptions.
- Redirects for known old routes.

Frauenstreik 2021 was corrected to 14 June using the original timestamp in Europe/Zurich. Distinct body images in the podcast and MINDS stories are retained alongside their cover images. The homepage's introductory copy is redesigned; historical records retain their original content. Swiss committee information is labelled as the historical 2022 roster.

The accreditation page's source contains a video credit, but a playable video URL could not be recovered. Older duplicate static member/interview pages were not individually word-compared; the current canonical profiles and stories were checked. Historical external links remain as provided by the source and were not all independently revalidated.

## Contact and membership

Contact and mailing-list requests open an email draft to 500wsbern@gmail.com. They do not automatically subscribe anyone. Historical campaigns are archives, not active signature forms. Wix contacts, mailing-list subscribers and other private administrative data have not been imported into this public repository.

## Moving to the association later

Create an association-owned repository and copy the contents of `500ws/` to its root. Move the Pages CMS configuration to that root, remove `500ws/` from its input and content paths, and set media output to `/assets`. Update existing content media prefixes from `/500ws/assets/` to `/assets/`. The build also normalizes both prefixes for portable public pages.

Adapt `.github/workflows/500ws-content.yml` to the new repository root, enable GitHub Pages from `main` and `/(root)`, and connect Pages CMS to the new repository. Update the login setup text. Remove the prototype `noindex` meta tag from the page template when the final site is approved. Verify domain ownership and configure the existing Infomaniak domain using GitHub's current documentation. Keep email DNS records if domain mail is still used.

No subscriptions, DNS, domain registrations or email services were changed by publishing this prototype.

## Attribution

Original content and photographs: https://www.500womenscientistsfribourgbern.ch/. Original authorship and rights remain unchanged. `asset-sources.json` records source media. The local Manrope font license is in `assets/Manrope-OFL.txt`.
