# How to publish the release (click-by-click)

You do this part in your web browser. It takes about 3 minutes. Nothing here
can break your code - a release is just a download page with your .exe attached.

## Step 1 - Open the release page

In your browser, go to this exact address:

    https://github.com/cloverarose-os/Buddy-AI/releases/new

(That is the repo's Releases section with a blank "new release" form open.)
If it asks you to log in to GitHub, do that first.

## Step 2 - Create the version tag

- You'll see a button/box labeled **"Choose a tag"**. Click it.
- Type exactly:  v0.1.0-alpha
- A little option will appear that says **"Create new tag: v0.1.0-alpha on
  publish"**. Click that option.

## Step 3 - Title

- In the **"Release title"** box, type:  Buddy AI v0.1.0-alpha

## Step 4 - Description

- Open the file `installer\RELEASE-NOTES-v0.1.0-alpha.md` (in this project),
  select all of it, copy it, and paste it into the big description box.

## Step 5 - Attach the installer (.exe)

- Find the box near the bottom that says
  **"Attach binaries by dropping them here or selecting them."**
- Click it (or drag the file onto it) and choose this file:

    C:\BuddyAI-repo\installer\Output\BuddyAI-Setup-v0.1.0-alpha.exe

- Wait for the upload bar to finish (it's ~2.4 MB, so it's quick).

## Step 6 - Mark it as alpha

- Find the checkbox labeled **"Set as a pre-release"** and CHECK it.
  (This is what puts the "alpha / pre-release" label on it.)
- Leave "Set as the latest release" UNchecked.

## Step 7 - Publish

- Click the green **"Publish release"** button.

Done. Your release now lives at:

    https://github.com/cloverarose-os/Buddy-AI/releases

Anyone can download the installer from there.

## If something looks wrong

You can edit or delete a release any time from the Releases page (pencil icon to
edit, then re-save). Deleting a release does not touch your code.
