// Front page: loops run only while their section is on screen, like the slides they came from.
const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => e.target.classList.toggle('on', e.isIntersecting));
}, { threshold: 0.08 });
document.querySelectorAll('[data-loop]').forEach((el) => io.observe(el));

// Pulse's page lived at / until this page took over. Old links with a section still land.
const moved = () => {
  if (/^#(vitals|sizes|claude|install)$/.test(location.hash)) location.replace('/pulse/' + location.hash);
};
moved();
addEventListener('hashchange', moved);
