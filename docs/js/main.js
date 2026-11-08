
/* =====================================================
   CROPGUARD AI - MAIN JAVASCRIPT
   Authentication + AI Detection + Database + History
   + Farmer Dashboard + Blockchain API
===================================================== */

const CG = {
    MAX_BYTES: 5 * 1024 * 1024,
    TYPES: ["image/jpeg", "image/png"],

    API_BASE: localStorage.getItem("cg_api") ||
        "http://127.0.0.1:5000/api",

    notice(el, msg, ok) {
        if (!el) return;
        el.textContent = msg;
        el.className = "small mt-3 " +
            (ok ? "text-success" : "text-danger");
    },

    session: {
        token() {
            return localStorage.getItem("cg_token");
        },

        user() {
            try {
                return JSON.parse(localStorage.getItem("cg_user"));
            } catch (error) {
                return null;
            }
        },

        save(token, user) {
            localStorage.setItem("cg_token", token);
            localStorage.setItem("cg_user", JSON.stringify(user));
        },

        clear() {
            localStorage.removeItem("cg_token");
            localStorage.removeItem("cg_user");
        }
    },

    async api(path, { method = "GET", body, auth = false } = {}) {
        const headers = {};

        if (body) {
            headers["Content-Type"] = "application/json";
        }

        if (auth) {
            headers["Authorization"] =
                "Bearer " + (CG.session.token() || "");
        }

        let response;

        try {
            response = await fetch(CG.API_BASE + path, {
                method,
                headers,
                body: body ? JSON.stringify(body) : undefined
            });
        } catch (error) {
            throw new Error(
                "Cannot connect to backend. Start Flask using python app.py."
            );
        }

        let data = {};

        try {
            data = await response.json();
        } catch (error) {
            // Ignore invalid JSON.
        }

        if (response.status === 401 && auth) {
            CG.session.clear();
        }

        if (!response.ok) {
            const apiError = new Error(
                data.error || data.message || "Request failed."
            );
            apiError.status = response.status;
            throw apiError;
        }

        return data;
    },

    requireLogin() {
        if (!CG.session.token()) {
            window.location.replace("login.html");
            return false;
        }
        return true;
    },

    navAuth() {
        const loginLink = document.querySelector(
            '.cg-nav a[href="login.html"]'
        );

        const registerLink = document.querySelector(
            '.cg-nav a[href="register.html"]'
        );

        if (!loginLink || !registerLink || !CG.session.token()) {
            return;
        }

        const user = CG.session.user() || {};
        const firstName = String(user.name || "Farmer").split(" ")[0];

        registerLink.parentElement.remove();

        const li = loginLink.parentElement;
        li.innerHTML = "";

        const hi = document.createElement("a");
        hi.className = "nav-link d-inline";
        hi.href = "dashboard.html";
        hi.textContent = "Hi, " + firstName;

        const logout = document.createElement("button");
        logout.className = "btn btn-outline-success btn-sm ms-2";
        logout.type = "button";
        logout.textContent = "Log out";

        logout.addEventListener("click", async () => {
            try {
                await CG.api("/auth/logout", {
                    method: "POST",
                    auth: true
                });
            } catch (error) {
                // Clear local session even if logout fails.
            }

            CG.session.clear();
            window.location.href = "index.html";
        });

        li.append(hi, logout);
    },

    authForm(id) {
        const form = document.getElementById(id);
        if (!form) return;

        const isAuth = id === "authForm";
        const isRegister =
            isAuth && !!form.querySelector("#confirm");

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            form.classList.add("was-validated");

            const val = selector => {
                const element = form.querySelector(selector);
                return element ? element.value : "";
            };

            let output = form.querySelector(".cg-msg");

            if (!output) {
                output = document.createElement("p");
                output.className = "cg-msg";
                output.setAttribute("aria-live", "polite");
                form.appendChild(output);
            }

            let message = "";

            if (!form.checkValidity()) {
                message = "Please fill in every field correctly.";
            } else if (
                isRegister && val("#password").length < 8
            ) {
                message = "Password must be at least 8 characters.";
            } else if (
                isRegister &&
                !(/[A-Za-z]/.test(val("#password")) &&
                  /\d/.test(val("#password")))
            ) {
                message =
                    "Password needs at least one letter and one number.";
            } else if (
                isRegister &&
                val("#password") !== val("#confirm")
            ) {
                message = "Passwords do not match.";
            }

            if (message) {
                return CG.notice(output, message, false);
            }

            if (!isAuth) {
                return CG.notice(
                    output,
                    "Your message is valid, but message sending is not connected yet.",
                    true
                );
            }

            const button = form.querySelector(
                'button[type="submit"]'
            );

            if (button) button.disabled = true;

            try {
                if (isRegister) {
                    await CG.api("/auth/register", {
                        method: "POST",
                        body: {
                            name: val("#name"),
                            email: val("#email"),
                            password: val("#password")
                        }
                    });

                    CG.notice(
                        output,
                        "Account created. Please log in.",
                        true
                    );

                    setTimeout(() => {
                        window.location.href = "login.html";
                    }, 1200);

                } else {
                    const result = await CG.api("/auth/login", {
                        method: "POST",
                        body: {
                            email: val("#email"),
                            password: val("#password")
                        }
                    });

                    CG.session.save(result.token, result.user);
                    window.location.href = "dashboard.html";
                }

            } catch (error) {
                CG.notice(output, error.message, false);
                if (button) button.disabled = false;
            }
        });
    },

    detection() {
        const input = document.getElementById("leafInput");
        const drop = document.getElementById("dropzone");
        const wrap = document.getElementById("previewWrap");
        const img = document.getElementById("preview");
        const msg = document.getElementById("fileMsg");
        const go = document.getElementById("analyzeBtn");
        const clr = document.getElementById("clearBtn");
        const box = document.getElementById("resultBox");

        if (!input || !drop || !wrap || !img ||
            !msg || !go || !clr || !box) {
            console.error("CropGuard detection elements are missing.");
            return;
        }

        let selectedFile = null;
        let objectUrl = null;

        const reset = () => {
            input.value = "";
            selectedFile = null;
            wrap.classList.add("d-none");

            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = null;
            }

            img.removeAttribute("src");
            go.disabled = true;
            clr.disabled = true;
            msg.textContent = "";

            box.innerHTML = `
                <div class="cg-empty">
                    <i class="bi bi-search"></i>
                    <h3>No result yet</h3>
                    <p>Choose a photo and select Analyze leaf.</p>
                </div>
            `;
        };

        const load = (file) => {
            msg.textContent = "";
            if (!file) return;

            const isAllowedType =
                CG.TYPES.includes(file.type) ||
                /\.(jpe?g|png)$/i.test(file.name || "");

            if (!isAllowedType) {
                selectedFile = null;
                go.disabled = true;
                msg.textContent =
                    "Unsupported image. Please select JPG or PNG.";
                return;
            }

            if (file.size > CG.MAX_BYTES) {
                selectedFile = null;
                go.disabled = true;
                msg.textContent =
                    "Image is larger than 5 MB. Select a smaller image.";
                return;
            }

            selectedFile = file;

            if (objectUrl) URL.revokeObjectURL(objectUrl);

            objectUrl = URL.createObjectURL(file);
            img.src = objectUrl;
            wrap.classList.remove("d-none");
            go.disabled = false;
            clr.disabled = false;

            box.innerHTML = `
                <div class="cg-empty">
                    <i class="bi bi-search"></i>
                    <h3>Ready to analyze</h3>
                    <p>Click Analyze leaf to detect possible crop diseases.</p>
                </div>
            `;
        };

        if (drop.tagName.toLowerCase() !== "label") {
            drop.addEventListener("click", () => input.click());
        }

        input.addEventListener("change", () => {
            if (input.files && input.files.length > 0) {
                load(input.files[0]);
            }
        });

        clr.addEventListener("click", reset);

        ["dragenter", "dragover"].forEach(eventName => {
            drop.addEventListener(eventName, event => {
                event.preventDefault();
                drop.classList.add("drag");
            });
        });

        ["dragleave", "drop"].forEach(eventName => {
            drop.addEventListener(eventName, event => {
                event.preventDefault();
                drop.classList.remove("drag");
            });
        });

        drop.addEventListener("drop", event => {
            const file = event.dataTransfer.files[0];
            if (file) load(file);
        });

        go.addEventListener("click", async () => {
            if (!selectedFile) return;

            go.disabled = true;
            clr.disabled = true;

            box.innerHTML = `
                <div class="cg-empty">
                    <i class="bi bi-hourglass-split"></i>
                    <h3>Analyzing leaf...</h3>
                    <p>CropGuard AI is processing your image. Please wait.</p>
                </div>
            `;

            try {
                const formData = new FormData();
                formData.append("image", selectedFile);

                const response = await fetch(
                    CG.API_BASE + "/predict",
                    {
                        method: "POST",
                        body: formData
                    }
                );

                let result = {};

                try {
                    result = await response.json();
                } catch (error) {
                    throw new Error("Backend returned an invalid response.");
                }

                if (!response.ok) {
                    throw new Error(result.error || "Prediction failed.");
                }

                const confidence = Number(result.confidence);

                if (!Number.isFinite(confidence)) {
                    throw new Error("Invalid confidence returned by backend.");
                }

                const statusColor =
                    confidence < 60 ? "danger" :
                    confidence < 80 ? "warning" : "success";

                box.innerHTML = `
                    <h5 class="text-success mb-3">
                        <i class="bi bi-activity"></i>
                        AI Detection Result
                    </h5>
                    <div class="alert alert-${statusColor}">
                        <strong id="cgDisease"></strong><br>
                        <span id="cgCondition"></span>
                    </div>
                    <div class="cg-result-item">
                        <strong>Model confidence</strong>
                        <p id="cgConfidence"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Confidence status</strong>
                        <p id="cgStatus"></p>
                    </div>
                    <div class="alert alert-${statusColor}">
                        <strong>Diagnosis warning</strong>
                        <p id="cgWarning" class="mb-0"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Severity</strong>
                        <p id="cgSeverity"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Symptoms</strong>
                        <p id="cgSymptoms"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Treatment</strong>
                        <p id="cgTreatment"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Chemical recommendation</strong>
                        <p id="cgChemical"></p>
                    </div>
                    <div class="cg-result-item">
                        <strong>Prevention</strong>
                        <p id="cgPrevention"></p>
                    </div>
                    <hr>
                    <small class="text-muted">
                        AI predictions are guidance, not a guaranteed diagnosis.
                        Confirm with a local agricultural expert before applying pesticides.
                    </small>
                `;

                const setText = (id, value) => {
                    const element = document.getElementById(id);
                    if (element) {
                        element.textContent = value || "Not available";
                    }
                };

                setText("cgDisease", result.crop_disease || result.disease);
                setText("cgCondition", result.condition);
                setText("cgConfidence", confidence.toFixed(2) + "%");
                setText("cgStatus", result.confidence_status);
                setText("cgWarning", result.diagnosis_warning);
                setText("cgSeverity", result.severity);
                setText("cgSymptoms", result.symptoms);
                setText("cgTreatment", result.treatment);
                setText("cgChemical", result.chemical_recommendation);
                setText("cgPrevention", result.prevention);

                if (CG.session.token()) {
                    try {
                        const rawLabel = String(
                            result.crop_disease || result.disease || ""
                        ).trim();

                        const supportedCrops = [
                            "Tomato", "Potato", "Pepper",
                            "Corn", "Apple", "Grape"
                        ];

                        let crop = supportedCrops.find(name =>
                            name.toLowerCase() ===
                            String(result.crop || "").trim().toLowerCase()
                        );

                        if (!crop) {
                            crop = supportedCrops.find(name =>
                                new RegExp(
                                    "^" + name + "(?:[_\\s-]|$)", "i"
                                ).test(rawLabel)
                            );
                        }

                        if (!crop) {
                            throw new Error(
                                "Could not identify a supported crop in the AI result."
                            );
                        }

                        let disease = String(
                            result.disease_name || result.disease || rawLabel
                        ).trim();

                        disease = disease.replace(
                            new RegExp("^" + crop + "[_\\s-]*", "i"),
                            ""
                        );

                        disease = disease
                            .replace(/_+/g, " ")
                            .replace(/\s+/g, " ")
                            .trim();

                        if (!disease || disease.length < 2) {
                            disease = String(
                                result.condition || "Unknown condition"
                            ).trim();
                        }

                        const saved = await CG.api("/detections", {
                            method: "POST",
                            auth: true,
                            body: {
                                crop,
                                disease,
                                confidence: confidence / 100,
                                notes: String(result.symptoms || "").slice(0, 500)
                            }
                        });

                        const savedMessage = document.createElement("div");
                        savedMessage.className = "alert alert-success mt-3";
                        savedMessage.textContent =
                            "Farm record saved successfully. Record ID: " +
                            saved.detection.id;
                        box.appendChild(savedMessage);

                    } catch (saveError) {
                        const saveMessage = document.createElement("div");
                        saveMessage.className = "alert alert-warning mt-3";
                        saveMessage.textContent =
                            "AI prediction succeeded, but saving the farm record failed: " +
                            saveError.message;
                        box.appendChild(saveMessage);
                    }
                } else {
                    const loginMessage = document.createElement("div");
                    loginMessage.className = "alert alert-info mt-3";
                    loginMessage.textContent =
                        "Log in to save this detection to your farm history.";
                    box.appendChild(loginMessage);
                }

            } catch (error) {
                box.innerHTML = `
                    <div class="alert alert-danger">
                        <h5>Prediction failed</h5>
                        <p id="cgError"></p>
                    </div>
                `;
                document.getElementById("cgError").textContent = error.message;

            } finally {
                go.disabled = !selectedFile;
                clr.disabled = !selectedFile;
            }
        });
    },

    async history() {
        if (!CG.requireLogin()) return;

        const body = document.getElementById("historyBody");
        const empty = document.getElementById("historyEmpty");
        if (!body || !empty) return;

        try {
            const result = await CG.api(
                "/detections?per_page=50",
                { auth: true }
            );

            body.innerHTML = "";

            result.detections.forEach(detection => {
                const tr = document.createElement("tr");
                const rawDate = String(detection.created_at || "");
                const parsedDate = new Date(
                    rawDate.replace(" ", "T") + "Z"
                );
                const date = Number.isNaN(parsedDate.getTime())
                    ? rawDate
                    : parsedDate.toLocaleString();

                [
                    date,
                    detection.crop,
                    detection.disease,
                    Math.round(Number(detection.confidence) * 100) + "%",
                    detection.blockchain_tx ? "Registered" : "Not registered"
                ].forEach(value => {
                    const td = document.createElement("td");
                    td.textContent = value ?? "";
                    tr.appendChild(td);
                });

                body.appendChild(tr);
            });

            empty.classList.toggle("d-none", result.detections.length > 0);

        } catch (error) {
            if (error.status === 401) {
                window.location.replace("login.html");
                return;
            }

            const heading = empty.querySelector("h3");
            const paragraph = empty.querySelector("p");

            if (heading) heading.textContent = "Could not load history";
            if (paragraph) paragraph.textContent = error.message;
        }
    },

    async dashboard() {
        if (!CG.requireLogin()) return;

        const message = document.getElementById("dashboardMessage");
        const totalLeaves = document.getElementById("totalLeaves");
        const healthyResults = document.getElementById("healthyResults");
        const diseasesFound = document.getElementById("diseasesFound");
        const blockchainRecords = document.getElementById("blockchainRecords");
        const recentEmpty = document.getElementById("recentEmpty");
        const recentTableWrap = document.getElementById("recentTableWrap");
        const recentBody = document.getElementById("recentBody");

        if (
            !message || !totalLeaves || !healthyResults ||
            !diseasesFound || !blockchainRecords ||
            !recentEmpty || !recentTableWrap || !recentBody
        ) {
            console.error("CropGuard dashboard elements are missing.");
            return;
        }

        try {
            const result = await CG.api(
                "/detections?per_page=100",
                { auth: true }
            );

            const detections = result.detections || [];
            const total = Number(result.total ?? detections.length);

            const healthy = detections.filter(detection =>
                String(detection.disease || "")
                    .toLowerCase().includes("healthy")
            ).length;

            const registered = detections.filter(detection =>
                Boolean(detection.blockchain_tx)
            ).length;

            totalLeaves.textContent = total;
            healthyResults.textContent = healthy;
            diseasesFound.textContent = Math.max(0, total - healthy);
            blockchainRecords.textContent = registered;

            recentBody.innerHTML = "";

            if (detections.length === 0) {
                recentEmpty.classList.remove("d-none");
                recentTableWrap.classList.add("d-none");
            } else {
                recentEmpty.classList.add("d-none");
                recentTableWrap.classList.remove("d-none");

                detections.slice(0, 5).forEach(detection => {
                    const tr = document.createElement("tr");
                    const rawDate = String(detection.created_at || "");
                    const parsedDate = new Date(
                        rawDate.replace(" ", "T") + "Z"
                    );
                    const date = Number.isNaN(parsedDate.getTime())
                        ? rawDate
                        : parsedDate.toLocaleString();

                    const values = [
                        date,
                        detection.crop || "",
                        detection.disease || "",
                        Math.round(Number(detection.confidence) * 100) + "%",
                        detection.blockchain_tx ? "Registered" : "Not registered"
                    ];

                    values.forEach(value => {
                        const td = document.createElement("td");
                        td.textContent = value;
                        tr.appendChild(td);
                    });

                    recentBody.appendChild(tr);
                });
            }

            message.className = "alert alert-success";
            message.textContent =
                "Your farm dashboard is connected successfully.";

        } catch (error) {
            message.className = "alert alert-danger";
            message.textContent =
                "Could not load dashboard: " + error.message;

            if (error.status === 401) {
                CG.session.clear();
                window.location.replace("login.html");
            }
        }
    }
};

// =====================================================
// MAKE CROPGUARD AVAILABLE TO ALL PAGE SCRIPTS
// =====================================================

window.CG = CG;

// =====================================================
// PAGE INITIALIZATION
// =====================================================

document.addEventListener("DOMContentLoaded", () => {
    CG.navAuth();
});