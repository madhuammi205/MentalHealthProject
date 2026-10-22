
const chatBox = document.getElementById("chat-box");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");
const finishButton = document.getElementById("finish-button");
const typing = document.getElementById("typing");
const moodOptions = document.getElementById("mood-options");

let busy = false;
let finished = false;

function addMessage(message, sender, messageId = null) {
    const div = document.createElement("div");
    div.className = "message " + sender + "-message";
    div.dataset.role = sender;

    if (messageId !== null) {
        div.dataset.messageId = messageId;
    }

    const text = document.createElement("span");
    text.className = "message-text";
    text.textContent = message;
    div.appendChild(text);

    if (sender === "user" && messageId !== null) {
        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "edit-message-button";
        editButton.textContent = "✏️ Edit";
        editButton.addEventListener("click", function () {
            editMessage(div);
        });
        div.appendChild(editButton);
    }

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;

    return div;
}

async function sendMessage(message, finish = false, userBubble = null) {
    if (busy || finished) return;

    busy = true;
    sendButton.disabled = true;
    finishButton.disabled = true;
    typing.hidden = false;
    moodOptions.hidden = true;

    try {
        const response = await fetch("/chat/message", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                finish: finish
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Please try again.");
        }

        if (data.finished && data.redirect_url) {
            finished = true;
            window.location.href = data.redirect_url;
            return;
        }

        if (userBubble && data.user_message_id) {
            userBubble.dataset.messageId = data.user_message_id;

            const editButton = document.createElement("button");
            editButton.type = "button";
            editButton.className = "edit-message-button";
            editButton.textContent = "✏️ Edit";
            editButton.addEventListener("click", function () {
                editMessage(userBubble);
            });

            userBubble.appendChild(editButton);
        }

        addMessage(data.reply, "bot");

        if (data.finished) {
            finished = true;
            userInput.disabled = true;
            sendButton.disabled = true;
            finishButton.textContent = "🌿 Session completed";
        }

    } catch (error) {
        console.error("Chat error:", error);

        addMessage(
            "Sorry, I couldn't connect just now. Please try again. 💜",
            "bot"
        );

    } finally {
        busy = false;
        typing.hidden = true;

        if (!finished) {
            sendButton.disabled = false;
            finishButton.disabled = false;
            userInput.focus();
        }
    }
}

async function editMessage(messageBubble) {
    if (busy || finished) return;

    const messageId = Number(messageBubble.dataset.messageId);
    const textElement = messageBubble.querySelector(".message-text");

    if (!messageId || !textElement) {
        alert("This answer cannot be edited. Please try again.");
        return;
    }

    const originalText = textElement.textContent;

    const editor = document.createElement("textarea");
    editor.value = originalText;
    editor.maxLength = 1000;
    editor.rows = 3;
    editor.className = "edit-message-input";
    editor.setAttribute("aria-label", "Edit your answer");

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.textContent = "💾 Save";
    saveButton.className = "save-edit-button";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.className = "cancel-edit-button";

    const editorContainer = document.createElement("div");
    editorContainer.className = "message-editor";
    editorContainer.append(editor, saveButton, cancelButton);

    const editButton = messageBubble.querySelector(".edit-message-button");

    textElement.hidden = true;
    if (editButton) editButton.hidden = true;
    messageBubble.appendChild(editorContainer);

    cancelButton.addEventListener("click", function () {
        editorContainer.remove();
        textElement.hidden = false;
        if (editButton) editButton.hidden = false;
    });

    saveButton.addEventListener("click", async function () {
        const correctedText = editor.value.trim();

        if (!correctedText) {
            alert("Please enter your answer.");
            return;
        }

        if (correctedText.length > 1000) {
            alert("Your answer must be 1000 characters or fewer.");
            return;
        }

        if (correctedText === originalText) {
            cancelButton.click();
            return;
        }

        busy = true;
        saveButton.disabled = true;
        cancelButton.disabled = true;
        editor.disabled = true;
        typing.hidden = false;

        try {
            const response = await fetch("/chat/edit-message", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    message_id: messageId,
                    content: correctedText
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error || "Could not update your answer."
                );
            }

            textElement.textContent = data.corrected_content;
            editorContainer.remove();
            textElement.hidden = false;

            if (editButton) editButton.hidden = false;

            // Remove all displayed messages after the corrected answer.
            let next = messageBubble.nextElementSibling;

            while (next) {
                const following = next.nextElementSibling;
                next.remove();
                next = following;
            }

            // Show the regenerated AI question.
            addMessage(data.reply, "bot");

        } catch (error) {
            console.error("Edit error:", error);
            alert(error.message || "Unable to edit your answer.");

            editorContainer.remove();
            textElement.hidden = false;
            if (editButton) editButton.hidden = false;

        } finally {
            busy = false;
            typing.hidden = true;
            sendButton.disabled = false;
            finishButton.disabled = false;
            userInput.focus();
        }
    });

    editor.focus();
}

chatForm.addEventListener("submit", function (event) {
    event.preventDefault();

    const message = userInput.value.trim();

    if (!message || busy || finished) return;

    const userBubble = addMessage(message, "user");
    userInput.value = "";

    sendMessage(message, false, userBubble);
});

moodOptions.querySelectorAll("button").forEach(function (button) {
    button.addEventListener("click", function () {
        const mood = button.dataset.mood;

        if (!mood || busy || finished) return;

        const userBubble = addMessage(mood, "user");
        sendMessage(mood, false, userBubble);
    });
});

finishButton.addEventListener("click", function () {
    if (busy || finished) return;

    sendMessage("", true);
});
