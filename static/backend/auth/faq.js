const pageCardGrid = document.querySelector('.page-card-grid');
const CARD_MOVE_DURATION_MS = 320;

function getGridColumnCount() {
  if (window.innerWidth <= 736) {
    return 1;
  }

  if (window.innerWidth <= 980) {
    return 2;
  }

  return 3;
}

function captureCardPositions() {
  if (!pageCardGrid) {
    return new Map();
  }

  const positions = new Map();
  pageCardGrid.querySelectorAll('.page-card').forEach((card) => {
    positions.set(card, card.getBoundingClientRect());
  });
  return positions;
}

function animateCardReflow(beforePositions) {
  if (!pageCardGrid) {
    return;
  }

  pageCardGrid.querySelectorAll('.page-card').forEach((card) => {
    const previousBox = beforePositions.get(card);
    const currentBox = card.getBoundingClientRect();

    if (!previousBox) {
      return;
    }

    const deltaX = previousBox.left - currentBox.left;
    const deltaY = previousBox.top - currentBox.top;

    if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
      return;
    }

    card.style.transition = 'none';
    card.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
    card.getBoundingClientRect();
    card.style.transition = `transform ${CARD_MOVE_DURATION_MS}ms ease`;
    card.style.transform = '';

    window.setTimeout(() => {
      if (!card.classList.contains('page-card-expanded')) {
        card.style.transition = '';
      }
    }, CARD_MOVE_DURATION_MS);
  });
}

function restoreDefaultCardOrder() {
  if (!pageCardGrid) {
    return;
  }

  const cards = Array.from(pageCardGrid.querySelectorAll('.page-card'));
  cards
    .sort((left, right) => Number(left.dataset.order) - Number(right.dataset.order))
    .forEach((card) => pageCardGrid.appendChild(card));
}

function moveExpandedCardBelowItsRow(card) {
  if (!pageCardGrid) {
    return;
  }

  const columnCount = getGridColumnCount();
  const cardOrder = Number(card.dataset.order);
  const rowStart = Math.floor(cardOrder / columnCount) * columnCount;
  const rowEnd = rowStart + columnCount - 1;
  const cards = Array.from(pageCardGrid.querySelectorAll('.page-card'))
    .sort((left, right) => Number(left.dataset.order) - Number(right.dataset.order));

  const anchorCard = cards.findLast((item) => Number(item.dataset.order) <= rowEnd);

  if (!anchorCard) {
    return;
  }

  if (anchorCard === card) {
    return;
  }

  anchorCard.insertAdjacentElement('afterend', card);
}

function setCardExpanded(card, expanded) {
  const details = card.querySelector('.page-card-details');
  const button = card.querySelector('.page-card-toggle');

  if (!details || !button) {
    return;
  }

  card.classList.toggle('page-card-expanded', expanded);
  details.hidden = !expanded;
  button.setAttribute('aria-expanded', String(expanded));
  button.textContent = expanded ? 'Collapse' : 'Extend';
}

document.querySelectorAll('.page-card-toggle').forEach((button) => {
  button.addEventListener('click', () => {
    const card = button.closest('.page-card');

    if (!card || !pageCardGrid) {
      return;
    }

    const beforePositions = captureCardPositions();
    const isExpanded = button.getAttribute('aria-expanded') === 'true';
    const expandedCard = pageCardGrid.querySelector('.page-card-expanded');

    if (expandedCard && expandedCard !== card) {
      setCardExpanded(expandedCard, false);
      restoreDefaultCardOrder();
    }

    if (isExpanded) {
      setCardExpanded(card, false);
      restoreDefaultCardOrder();
      animateCardReflow(beforePositions);
      return;
    }

    setCardExpanded(card, true);
    moveExpandedCardBelowItsRow(card);
    animateCardReflow(beforePositions);
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
});
