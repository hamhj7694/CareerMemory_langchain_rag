import { ExperienceUnitsProposalCard } from './experience-units/index.js';
import { LegacyProposalCard } from './old/LegacyProposalCard.jsx';

export function ProposalCard(props) {
  if (props.proposal?.contractVersion === 'experience-units-v2') {
    return <ExperienceUnitsProposalCard {...props} />;
  }
  return <LegacyProposalCard {...props} />;
}
