# English source and Vietnamese translations

English is the development language, source language, and fallback for Dearly. New installations start in English. An explicitly saved Vietnamese preference remains Vietnamese. Unknown language preferences fall back to English. Language names in the picker use their own names: English and Tiếng Việt.

## Source conventions

- Use English identifiers, comments, fixture defaults, and documentation.
- Write static interface text as `L("English source text")`. Add the English key and Vietnamese translation to `Dearly/Localizable.xcstrings`; its source language and the Xcode development region are both `en`.
- Use `LF("With %1$@", name)` for variable text. Translations may reorder positional placeholders. Values are inserted after translation, so user names, journal text, and percent signs in user content remain unchanged.
- Catalog entries used through the custom helpers are marked manual so Xcode keeps them. Keep the English value equal to the key and match placeholders in both languages.
- Keep user-written profile fields, journals, messages, reports, and review notes as entered. Do not use their text as localization keys.
- Use stable English identifiers for structured values: `SupportStyle` encodes `listen`, `relate`, or `brainstorm`; its localized `title` is only for display. API field names, roles, actions, and audience identifiers are independent of language.

Vietnamese in source code is limited to the language picker's own name and explicit legacy decoding maps. Other Vietnamese product text belongs in translation resources.

## Backend errors

Backend call sites pass English templates to `fail(...)` or `error_response(...)`. Vietnamese translations live in `backend/translations.vi.json`. Dynamic errors use named fields, for example `fail("Missing or invalid field {field}.", field=key)`.

Requests without a supported language preference receive English errors. `Accept-Language: vi` or `vi-VN` selects Vietnamese; supported language ranges are compared by quality and order. The iOS API client sends its current app language on each request. Error responses include `Content-Language`, `Vary: Accept-Language`, and `Cache-Control: no-store`. Validation errors do not echo submitted credentials. Upload-limit errors use the same translation path.

Successful DTOs keep the same identifiers and user content in either language; choosing Vietnamese does not change stored values.

## Compatibility and upgrade

SQLite v4 converts only known Vietnamese support values in profiles and journals. Existing free-form interests, conversation pace, nicknames, biographies, and journal text remain untouched. New accounts receive English default interests and conversation pace. The new iOS decoder reads both the canonical identifiers and legacy Vietnamese support values. The backend accepts both input forms and writes canonical identifiers.

Upgrade the app and backend together: older iOS builds expect Vietnamese enum values and cannot read the new response identifiers. Follow the backend backup and upgrade instructions before migration. The historical native JSON fixtures intentionally retain legacy values to exercise compatibility.

## Checks

Backend tests cover language negotiation, static and parameterized errors, upload limits, credential-safe validation, canonical and legacy support inputs, v3 migration, repeated startup, and new-account defaults after an older schema upgrade. Resource checks verify English source configuration, complete Vietnamese translations, and matching placeholders. Native tests exercise default/fallback language, Vietnamese lookup and formatting, literal user content, and old/new support decoding.
