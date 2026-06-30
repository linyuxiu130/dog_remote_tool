from __future__ import annotations


def local_paths_from_event(event) -> list[str]:
    return [
        url.toLocalFile()
        for url in event.mimeData().urls()
        if url.isLocalFile() and url.toLocalFile()
    ]


def event_has_local_paths(event) -> bool:
    mime = event.mimeData()
    return mime.hasUrls() and any(url.isLocalFile() for url in mime.urls())


def accept_local_paths_or_ignore(event) -> None:
    if event_has_local_paths(event):
        event.acceptProposedAction()
    else:
        event.ignore()
