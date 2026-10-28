# Legacy experience proposal UI

`InlineProposalCard.jsx`, the `experience_proposal` action, and the
`/experience-proposal` endpoints are the read/update compatibility path for
stored proposals created before `experience-units-v2`.

New integrated conversation analyses render through
`ExperienceUnitsProposalCard.jsx`. Do not remove this legacy path until stored
messages and proposals have been migrated or their retention period has ended.
