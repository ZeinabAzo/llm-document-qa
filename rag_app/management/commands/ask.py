from django.core.management.base import BaseCommand, CommandError

from rag_app import services


class Command(BaseCommand):
    help = (
        "Ask a question about the uploaded documents (saved to the Q&A history). "
        "Run without a question to ask several in a row."
    )

    def add_arguments(self, parser):
        parser.add_argument("question", nargs="*", help="The question. Leave empty for interactive mode.")
        parser.add_argument("--top-k", type=int, default=None, help="Passages to retrieve (default 5).")

    def handle(self, *args, **options):
        top_k = options["top_k"]
        if options["question"]:
            self._answer(" ".join(options["question"]), top_k, raise_errors=True)
            return

        # Interactive mode: the model and index load once, so later questions are fast.
        self.stdout.write("Type a question and press Enter. Press Enter on an empty line to quit.\n")
        while True:
            try:
                question = input("Question: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question:
                break
            self._answer(question, top_k, raise_errors=False)

    def _answer(self, question: str, top_k: int | None, raise_errors: bool) -> None:
        self.stdout.write("Thinking...")
        try:
            entry = services.ask(question, top_k)
        except services.QAError as exc:
            if raise_errors:
                raise CommandError(str(exc)) from exc
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.SUCCESS(f"\n{entry.answer}\n"))
        self.stdout.write("Sources:")
        for source in entry.sources:
            section = f" > {source['section']}" if source["section"] else ""
            self.stdout.write(f"  [{source['number']}] {source['document_title']}{section}")
        self.stdout.write(f"({entry.latency_ms / 1000:.1f} s, saved as history entry #{entry.pk})\n")
