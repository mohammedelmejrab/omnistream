import urllib.request

urllib.request.urlopen(
    "https://ntfy.sh/omnistream_hmoodi_alerts", data=b"Milestone 1 execution complete!"
)
print("Notification sent successfully!")
