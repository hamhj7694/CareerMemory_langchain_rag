import { InlineProposalCard } from '../InlineProposalCard.jsx';

// Compatibility boundary for stored pre-v2 proposal messages.
export function LegacyProposalCard(props) {
  return <InlineProposalCard {...props} />;
}
