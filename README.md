# Submission Quran Reader — v5

## Reading
- `q2:225` or `Q2:225`: one verse.
- `q1:1-7`: a range within one chapter.
- `/quran verse:1:1-7`: slash-command equivalent.
- `/appendix number:2`: Appendix 2, with page navigation and PDF download.
- `/appendix`: index of all 38 appendices.

The supplied English book is bundled locally. The reader shows images cropped from the edition, with God capitalised as “God”. There are no external scripture service calls or source-site buttons. Long passages have page navigation. At printed page boundaries, surrounding notes can appear. Buttons last one hour; run the command again afterward.

## Saved Quran study progress
- `/study_update verse:1:1-7`: save the passage actually read. Host confirmation is deliberate; verse lookups do not change study progress.
- `/study_latest`: display the latest saved passage and last verse.
- To seed the reader with previous study progress, use `/study_update` with the last known passage. This does not import or modify the verification bot's older study records.
- Set `STUDY_HOST_IDS` to the comma-separated Discord user IDs permitted to update progress. Server administrators can also update it. No Administrator grant is needed for designated hosts.
- Attach a Railway volume to THIS reader service at `/data`. The study history is written there. `READER_DATA_DIR` can override the path. A volume is required to retain progress across redeployments. Run one replica.

## Deployment
1. Extract this ZIP. Upload all files and the complete appendices directory to the root of the existing Quran Reader GitHub repository. Keep filenames unchanged. Do not upload to the verification bot repository.
2. Keep the reader's existing `DISCORD_TOKEN`. Message Content Intent must remain enabled for q/Q messages.
3. Add the reader's `/data` volume and `STUDY_HOST_IDS` as above.
4. Commit to the branch Railway deploys and wait for Active. The startup line identifies Quran Reader v5.
5. Test `q1:1-7`, `/appendix number:2`, `/study_update verse:1:1-7`, then `/study_latest`.

The bot needs View Channel, Send Messages, Embed Links and Attach Files in the configured reading chats. Existing `GUILD_ID` and `READER_CHANNEL_IDS` overrides remain supported. Default reading channels are the four existing VC text chats. The study command names differ from the verification bot's study commands to avoid confusion. Existing verification tickets, roles, and records are untouched.
