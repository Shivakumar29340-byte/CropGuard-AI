
"""
CropGuard AI - Plant Disease Training
Dataset: PlantVillage
Model: MobileNetV2 Transfer Learning
"""

import json
from pathlib import Path
from collections import Counter

import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.callbacks import (
    EarlyStopping,
    ModelCheckpoint,
    ReduceLROnPlateau
)

# -----------------------------
# 1. PROJECT PATHS
# -----------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset" / "PlantVillage"
MODEL_DIR = Path(__file__).resolve().parent / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODEL_DIR / "cropguard_model.keras"
LABEL_PATH = MODEL_DIR / "class_names.json"

IMAGE_SIZE = (224, 224)
BATCH_SIZE = 16
EPOCHS = 10
SEED = 42

print("TensorFlow version:", tf.__version__)
print("Dataset location:", DATASET_DIR)

if not DATASET_DIR.exists():
    raise FileNotFoundError(
        f"PlantVillage dataset not found: {DATASET_DIR}"
    )

# -----------------------------
# 2. LOAD DATASET
# -----------------------------

train_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR,
    validation_split=0.20,
    subset="training",
    seed=SEED,
    image_size=IMAGE_SIZE,
    batch_size=BATCH_SIZE,
    label_mode="int"
)

val_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET_DIR,
    validation_split=0.20,
    subset="validation",
    seed=SEED,
    image_size=IMAGE_SIZE,
    batch_size=BATCH_SIZE,
    label_mode="int"
)

class_names = train_ds.class_names
num_classes = len(class_names)

print("\nDetected disease categories:")
for i, name in enumerate(class_names):
    print(i, ":", name)

print("\nTotal classes:", num_classes)

# Save class names for Flask prediction
with open(LABEL_PATH, "w", encoding="utf-8") as f:
    json.dump(class_names, f, indent=4)

# -----------------------------
# 3. HANDLE CLASS IMBALANCE
# -----------------------------

valid_extensions = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif"
}

class_counts = {}

for class_name in class_names:
    folder = DATASET_DIR / class_name

    count = sum(
        1 for file in folder.rglob("*")
        if file.is_file()
        and file.suffix.lower() in valid_extensions
    )

    class_counts[class_name] = count

total_images = sum(class_counts.values())

class_weights = {}

for index, class_name in enumerate(class_names):
    count = class_counts[class_name]

    if count > 0:
        class_weights[index] = (
            total_images / (num_classes * count)
        )

print("\nClass image counts:")
for name, count in class_counts.items():
    print(name, ":", count)

# -----------------------------
# 4. OPTIMIZE DATA LOADING
# -----------------------------

AUTOTUNE = tf.data.AUTOTUNE

train_ds = train_ds.prefetch(AUTOTUNE)
val_ds = val_ds.prefetch(AUTOTUNE)

# -----------------------------
# 5. DATA AUGMENTATION
# -----------------------------

augmentation = tf.keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.10),
    layers.RandomZoom(0.10),
    layers.RandomContrast(0.10)
], name="data_augmentation")

# -----------------------------
# 6. LOAD MOBILENETV2
# -----------------------------

base_model = MobileNetV2(
    input_shape=(224, 224, 3),
    include_top=False,
    weights="imagenet"
)

# Freeze pretrained layers initially
base_model.trainable = False

# -----------------------------
# 7. BUILD CROPGUARD MODEL
# -----------------------------

inputs = layers.Input(shape=(224, 224, 3))

x = augmentation(inputs)

# MobileNetV2 expects pixel values from -1 to 1
x = layers.Rescaling(
    scale=1.0 / 127.5,
    offset=-1
)(x)

x = base_model(x, training=False)

x = layers.GlobalAveragePooling2D()(x)

x = layers.Dropout(0.30)(x)

outputs = layers.Dense(
    num_classes,
    activation="softmax"
)(x)

model = models.Model(inputs, outputs)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# -----------------------------
# 8. TRAINING CALLBACKS
# -----------------------------

callbacks = [
    ModelCheckpoint(
        filepath=str(MODEL_PATH),
        monitor="val_accuracy",
        save_best_only=True,
        verbose=1
    ),

    EarlyStopping(
        monitor="val_loss",
        patience=3,
        restore_best_weights=True,
        verbose=1
    ),

    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.2,
        patience=2,
        min_lr=0.000001,
        verbose=1
    )
]

# -----------------------------
# 9. TRAIN MODEL
# -----------------------------

print("\nStarting CropGuard AI training...")

history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    class_weight=class_weights,
    callbacks=callbacks
)

# -----------------------------
# 10. EVALUATE MODEL
# -----------------------------

print("\nEvaluating best saved model...")

best_model = tf.keras.models.load_model(MODEL_PATH)

loss, accuracy = best_model.evaluate(val_ds)

print("\nTraining completed!")
print("Validation accuracy:", round(accuracy * 100, 2), "%")
print("Validation loss:", round(loss, 4))

print("\nModel saved at:", MODEL_PATH)
print("Labels saved at:", LABEL_PATH)
print("\nCropGuard AI training finished successfully!")
