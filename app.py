#!/usr/bin/env python3
"""
===============================================================================
YOLO Annotator - Image Annotation Tool
===============================================================================

A lightweight, image annotation tool for creating YOLO format
datasets. Designed for marine survey data, side-scan sonar imagery, and 
large-format scientific images.

Author: Ahmed Fekry
LinkedIn: www.linkedin.com/in/ahmed-fekry07
Version: 1.0
License: MIT
Date: November 2025

Features:
- YOLO format annotation (class_id x_center y_center width height)
- Multi-class support with custom IDs
- Interactive editing with resize handles
- Undo/Redo functionality
- Keyboard shortcuts for efficiency
- Batch processing support
- Export selected or all annotations
- Clean, intuitive interface

===============================================================================
"""

import sys
import os
from pathlib import Path
from typing import List, Optional, Tuple
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsPixmapItem, QDockWidget, QListWidget,
    QListWidgetItem, QFileDialog, QInputDialog, QMessageBox,
    QWidget, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QPen, QColor, QBrush, QAction, QKeySequence,
    QPainter, QWheelEvent, QMouseEvent
)


# ============================================================================
# RESIZE HANDLE CLASS
# ============================================================================

class ResizeHandle(QGraphicsRectItem):
    """
    Interactive resize handle for bounding boxes.
    
    Displayed as small yellow squares at the corners of selected boxes.
    Allows users to resize boxes by dragging the handles.
    Handles are parented to their box, so they move together automatically.
    """
    
    def __init__(self, position: str, parent_bbox: QGraphicsRectItem):
        """
        Initialize a resize handle.
        
        Args:
            position: Position identifier ('top-left', 'top-right', etc.)
            parent_bbox: The graphics item of the parent bounding box
        """
        super().__init__(-5, -5, 10, 10)  # 10x10 handle centered on position
        self.position = position
        self.parent_bbox = parent_bbox
        
        # Visual appearance
        self.setBrush(QBrush(QColor(255, 255, 0)))  # Yellow fill
        self.setPen(QPen(QColor(0, 0, 0), 2))  # Black border
        
        # Make it movable
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        
        self.start_rect = None
        self.start_pos = None
    
    def mousePressEvent(self, event):
        """Handle mouse press - store initial state for resizing."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_rect = QRectF(self.parent_bbox.rect())
            self.start_pos = event.scenePos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move - resize the parent box based on handle drag."""
        if self.start_rect:
            delta = event.scenePos() - self.start_pos
            new_rect = QRectF(self.start_rect)
            
            # Adjust rectangle based on which handle is being dragged
            if 'top' in self.position:
                new_rect.setTop(self.start_rect.top() + delta.y())
            if 'bottom' in self.position:
                new_rect.setBottom(self.start_rect.bottom() + delta.y())
            if 'left' in self.position:
                new_rect.setLeft(self.start_rect.left() + delta.x())
            if 'right' in self.position:
                new_rect.setRight(self.start_rect.right() + delta.x())
            
            # Enforce minimum size (prevents box from collapsing)
            if new_rect.width() > 10 and new_rect.height() > 10:
                self.parent_bbox.setRect(new_rect.normalized())
                # Update handle positions
                if hasattr(self.scene(), 'update_resize_handles'):
                    self.scene().update_resize_handles()
                # Update label position and size
                if hasattr(self.scene(), 'update_box_label'):
                    self.scene().update_box_label(self.parent_bbox)


# ============================================================================
# BOUNDING BOX DATA CLASS
# ============================================================================

class BoundingBox:
    """
    Data structure representing a single bounding box annotation.
    
    Stores both the geometric data (rectangle) and metadata (class info, color).
    Handles conversion to YOLO format for export.
    """
    
    def __init__(self, rect: QRectF, class_id: int, class_name: str, color: Optional[QColor] = None):
        """
        Initialize a bounding box.
        
        Args:
            rect: QRectF defining the box geometry
            class_id: Integer class ID (0-indexed)
            class_name: Human-readable class name
            color: Optional custom color for this class
        """
        self.rect = rect
        self.class_id = class_id
        self.class_name = class_name
        self.color = color  # Custom color for this class
        self.graphics_item: Optional[QGraphicsRectItem] = None
    
    def to_yolo_format(self, image_width: int, image_height: int) -> str:
        """
        Convert box to YOLO format string.
        
        YOLO format: class_id x_center y_center width height
        All coordinates normalized to [0, 1] range.
        
        Args:
            image_width: Width of the image in pixels
            image_height: Height of the image in pixels
            
        Returns:
            String in YOLO format
        """
        # Calculate normalized coordinates
        x_center = (self.rect.left() + self.rect.right()) / 2.0 / image_width
        y_center = (self.rect.top() + self.rect.bottom()) / 2.0 / image_height
        width = self.rect.width() / image_width
        height = self.rect.height() / image_height
        
        # Ensure values are within valid range [0, 1]
        x_center = max(0.0, min(1.0, x_center))
        y_center = max(0.0, min(1.0, y_center))
        width = max(0.0, min(1.0, width))
        height = max(0.0, min(1.0, height))
        
        return f"{self.class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
    
    @staticmethod
    def from_yolo_format(line: str, image_width: int, image_height: int, 
                         class_name: str) -> Optional['BoundingBox']:
        """
        Create BoundingBox from YOLO format string.
        
        Args:
            line: YOLO format string
            image_width: Width of the image in pixels
            image_height: Height of the image in pixels
            class_name: Name of the class
            
        Returns:
            BoundingBox object or None if parsing fails
        """
        try:
            parts = line.strip().split()
            if len(parts) != 5:
                return None
            
            class_id = int(parts[0])
            x_center = float(parts[1]) * image_width
            y_center = float(parts[2]) * image_height
            width = float(parts[3]) * image_width
            height = float(parts[4]) * image_height
            
            # Convert from center coords to top-left coords
            x = x_center - width / 2
            y = y_center - height / 2
            
            rect = QRectF(x, y, width, height)
            return BoundingBox(rect, class_id, class_name)
        except (ValueError, IndexError):
            return None


# ============================================================================
# ANNOTATION SCENE CLASS
# ============================================================================

class AnnotationScene(QGraphicsScene):
    """
    Custom QGraphicsScene for managing image annotation.
    
    Handles:
    - Drawing new bounding boxes
    - Editing existing boxes
    - Resize handle management
    - Selection and highlighting
    - Undo/Redo functionality
    - Color coding by class
    
    Signals:
        box_created: Emitted when a new box is created
        box_selected: Emitted when a box is selected in the viewer
    """
    
    box_created = pyqtSignal()
    box_selected = pyqtSignal(object)  # Emits BoundingBox object
    
    def __init__(self, parent=None):
        """Initialize the annotation scene."""
        super().__init__(parent)
        
        # Image and drawing state
        self.image_item: Optional[QGraphicsPixmapItem] = None
        self.current_box: Optional[QGraphicsRectItem] = None
        self.start_point: Optional[QPointF] = None
        self.image_width: int = 0
        self.image_height: int = 0
        
        # Bounding boxes storage
        self.boxes: List[BoundingBox] = []
        self.selected_box: Optional[BoundingBox] = None
        self.editing_box: Optional[BoundingBox] = None
        self.resize_handles: List[ResizeHandle] = []
        
        # Current class for new boxes
        self.current_class_id: int = 0
        self.current_class_name: str = ""
        self.current_class_color: Optional[QColor] = None
        
        # Drawing mode control
        self.drawing_enabled: bool = True
        
        # Undo/Redo functionality
        self.undo_stack: List[List[BoundingBox]] = []
        self.redo_stack: List[List[BoundingBox]] = []
        
        # Custom colors for classes (class_id -> QColor)
        self.class_custom_colors: dict = {}
        
        # Default color scheme for classes (fallback)
        self.class_colors = [
            QColor(0, 255, 0, 150),      # Green
            QColor(255, 0, 0, 150),      # Red
            QColor(0, 0, 255, 150),      # Blue
            QColor(255, 255, 0, 150),    # Yellow
            QColor(255, 0, 255, 150),    # Magenta
            QColor(0, 255, 255, 150),    # Cyan
            QColor(255, 128, 0, 150),    # Orange
            QColor(128, 0, 255, 150),    # Purple
        ]
    
    def set_image(self, pixmap: QPixmap):
        """
        Load and display a new image.
        
        Clears all previous annotations and resets the scene state completely.
        
        Args:
            pixmap: QPixmap containing the image to annotate
        """
        try:
            # Finish any editing in progress
            if self.editing_box:
                self.finish_editing()
            
            # Remove resize handles first
            self.remove_resize_handles()
            
            # Clear selection
            self.selected_box = None
            self.editing_box = None
            self.current_box = None
            
            # Remove all box graphics items safely
            for bbox in self.boxes[:]:  # Use slice to iterate over copy
                if bbox.graphics_item:
                    try:
                        if bbox.graphics_item.scene() == self:
                            self.removeItem(bbox.graphics_item)
                        bbox.graphics_item = None
                    except:
                        pass
            
            # Clear boxes list
            self.boxes.clear()
            
            # Clear the entire scene
            self.clear()
            
            # Clear history
            self.undo_stack.clear()
            self.redo_stack.clear()
            
            # Add the new image
            self.image_item = QGraphicsPixmapItem(pixmap)
            self.addItem(self.image_item)
            self.setSceneRect(self.image_item.boundingRect())
            
            self.image_width = pixmap.width()
            self.image_height = pixmap.height()
            
        except Exception as e:
            print(f"Error in set_image: {e}")
            # Ensure scene is cleared even if error occurs
            self.clear()
            self.boxes.clear()
            self.image_item = QGraphicsPixmapItem(pixmap)
            self.addItem(self.image_item)
            self.setSceneRect(self.image_item.boundingRect())
            self.image_width = pixmap.width()
            self.image_height = pixmap.height()
    
    def get_box_color(self, class_id: int) -> QColor:
        """
        Get display color for a class ID.
        
        Uses custom color if set, otherwise falls back to default scheme.
        
        Args:
            class_id: The class ID
            
        Returns:
            QColor for this class
        """
        # Check if custom color exists for this class
        if class_id in self.class_custom_colors:
            return self.class_custom_colors[class_id]
        
        # Fall back to default color scheme
        return self.class_colors[class_id % len(self.class_colors)]
    
    def set_class_color(self, class_id: int, color: QColor):
        """
        Set custom color for a class.
        
        Args:
            class_id: The class ID
            color: QColor to use for this class
        """
        self.class_custom_colors[class_id] = color
    
    def set_current_class(self, class_id: int, class_name: str, color: Optional[QColor] = None):
        """
        Set the active class for new annotations.
        
        Args:
            class_id: ID of the class
            class_name: Name of the class
            color: Optional custom color for the class
        """
        self.current_class_id = class_id
        self.current_class_name = class_name
        self.current_class_color = color
        
        # Store custom color if provided
        if color:
            self.class_custom_colors[class_id] = color
    
    def mousePressEvent(self, event: QMouseEvent):
        """
        Handle mouse press events.
        
        Behavior depends on what was clicked:
        - Existing box: Select it
        - Resize handle: Let handle process it
        - Elsewhere: Deselect all and start new box (if class selected)
        """
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_enabled:
            # Check what was clicked
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            
            # If clicking on resize handle, let it handle the event
            if isinstance(item, ResizeHandle):
                super().mousePressEvent(event)
                return
            
            # If clicking on an existing box, select it
            if isinstance(item, QGraphicsRectItem) and item != self.current_box:
                self.select_box_by_item(item)
                super().mousePressEvent(event)
                return
            
            # Clicking anywhere else (including on image) - deselect and finish editing
            self.select_box(None)
            self.finish_editing()
            
            # Start drawing new box if class is selected
            if self.current_class_name:
                self.start_point = event.scenePos()
                self.current_box = QGraphicsRectItem()
                
                color = self.get_box_color(self.current_class_id)
                pen = QPen(color, 2, Qt.PenStyle.DashLine)
                self.current_box.setPen(pen)
                
                self.addItem(self.current_box)
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """
        Handle mouse move events.
        
        Updates the current box rectangle while drawing.
        """
        if self.current_box and self.start_point:
            # Update the rectangle as user drags
            current_point = event.scenePos()
            rect = QRectF(self.start_point, current_point).normalized()
            self.current_box.setRect(rect)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        Handle mouse release events.
        
        Finalizes the current box if it's large enough.
        Minimum size requirement prevents accidental tiny boxes.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.current_box:
            rect = self.current_box.rect()
            
            # Only create box if it's large enough (min 5x5 pixels)
            if rect.width() > 5 and rect.height() > 5:
                # Save current state for undo
                self.save_state()
                
                # Get color (custom or default)
                color = self.get_box_color(self.current_class_id)
                
                # Create bounding box data object with color
                bbox = BoundingBox(
                    rect, 
                    self.current_class_id, 
                    self.current_class_name,
                    color
                )
                bbox.graphics_item = self.current_box
                
                # Set final appearance (outline only, no fill)
                pen = QPen(color, 3)  # Thicker pen (3px)
                self.current_box.setPen(pen)
                # No brush - boxes are outline only
                
                # Add text label with class name
                self.add_box_label(self.current_box, self.current_class_name, color)
                
                self.boxes.append(bbox)
                self.box_created.emit()
            else:
                # Remove tiny box
                self.removeItem(self.current_box)
            
            self.current_box = None
            self.start_point = None
        
        super().mouseReleaseEvent(event)
    
    def select_box(self, bbox: Optional[BoundingBox]):
        """
        Select a bounding box.
        
        Highlights the selected box with a white border.
        
        Args:
            bbox: Box to select, or None to deselect all
        """
        # Deselect current box
        if self.selected_box and self.selected_box.graphics_item:
            color = self.get_box_color(self.selected_box.class_id)
            pen = QPen(color, 3)  # Thicker pen
            self.selected_box.graphics_item.setPen(pen)
        
        # Select new box
        self.selected_box = bbox
        if bbox and bbox.graphics_item:
            pen = QPen(QColor(255, 255, 255), 4)  # White highlight, extra thick
            bbox.graphics_item.setPen(pen)
    
    def select_box_by_item(self, item: QGraphicsRectItem):
        """
        Select a box by its graphics item.
        
        Also emits signal to synchronize with annotations list.
        
        Args:
            item: The graphics item representing the box
        """
        for i, bbox in enumerate(self.boxes):
            if bbox.graphics_item == item:
                self.select_box(bbox)
                # Emit signal for list synchronization
                self.box_selected.emit(bbox)
                break
    
    def delete_selected_boxes(self, indices: List[int]):
        """
        Delete boxes at specified indices.
        
        Args:
            indices: List of indices to delete (sorted descending)
        """
        self.save_state()
        
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self.boxes):
                bbox = self.boxes[i]
                if bbox.graphics_item:
                    self.removeItem(bbox.graphics_item)
                self.boxes.pop(i)
        
        self.selected_box = None
    
    def add_resize_handles(self, bbox: BoundingBox):
        """
        Add visible resize handles to a box for editing.
        
        Handles are parented to the box so they move together.
        
        Args:
            bbox: The bounding box to add handles to
        """
        if not bbox.graphics_item:
            return
        
        # Remove old handles
        self.remove_resize_handles()
        
        # Create handles at 4 corners
        rect = bbox.graphics_item.rect()
        
        positions = [
            ('top-left', rect.topLeft()),
            ('top-right', rect.topRight()),
            ('bottom-left', rect.bottomLeft()),
            ('bottom-right', rect.bottomRight())
        ]
        
        for position_name, pos in positions:
            handle = ResizeHandle(position_name, bbox.graphics_item)
            # Parent to box so they move together
            handle.setParentItem(bbox.graphics_item)
            handle.setPos(pos)
            self.resize_handles.append(handle)
    
    def remove_resize_handles(self):
        """Remove all resize handles from the scene."""
        for handle in self.resize_handles:
            if handle.scene() == self:
                self.removeItem(handle)
        self.resize_handles.clear()
    
    def update_resize_handles(self):
        """Update handle positions after box is resized."""
        if self.editing_box and self.editing_box.graphics_item and self.resize_handles:
            rect = self.editing_box.graphics_item.rect()
            
            # Positions relative to box (handles are children)
            positions = [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight()
            ]
            
            for i, handle in enumerate(self.resize_handles):
                if i < len(positions):
                    handle.setPos(positions[i])
    
    def finish_editing(self):
        """
        Finish editing mode.
        
        Saves changes, removes handles, and resets appearance.
        """
        if self.editing_box:
            # Update the BoundingBox rect from graphics item
            if self.editing_box.graphics_item:
                # Get the item's rectangle in scene coordinates
                item = self.editing_box.graphics_item
                rect_in_scene = item.mapRectToScene(item.rect())
                self.editing_box.rect = rect_in_scene
                
                # Reset to normal appearance
                color = self.get_box_color(self.editing_box.class_id)
                pen = QPen(color, 3)  # Thicker pen
                self.editing_box.graphics_item.setPen(pen)
                
                # Make non-movable
                self.editing_box.graphics_item.setFlag(
                    QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False
                )
            
            # Remove resize handles
            self.remove_resize_handles()
            
            self.editing_box = None
    
    def add_box_label(self, box_item: QGraphicsRectItem, class_name: str, color: QColor):
        """
        Add a text label showing the class name on the box.
        Label appears in a small box at the top-left corner.
        
        Args:
            box_item: The graphics rectangle item
            class_name: Name of the class to display
            color: Color for the label background
        """
        from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsRectItem as GRI
        
        # Create text item
        text_item = QGraphicsTextItem(class_name)
        # Always use black text
        text_color = QColor(0, 0, 0)  # Black text
        text_item.setDefaultTextColor(text_color)
        
        # Set font - smaller and bold
        from PyQt6.QtGui import QFont
        font = QFont()
        box_height = box_item.rect().height()
        font_size = int(box_height / 15)
        font_size = max(7, min(font_size, 14))
        font.setPointSize(font_size)
        font.setBold(True)
        text_item.setFont(font)
        
        # Get text dimensions
        text_rect = text_item.boundingRect()
        padding = 3  # Padding inside the label box
        
        # Create background rectangle for the label
        label_width = text_rect.width() + (padding * 2)
        label_height = text_rect.height() + (padding * 2)
        
        bg_rect = GRI(0, 0, label_width, label_height)
        bg_rect.setBrush(QBrush(color))
        bg_rect.setPen(QPen(color, 1))
        
        # Position background at top-left corner of the box (just outside)
        box_rect = box_item.rect()
        bg_rect.setPos(box_rect.left(), box_rect.top() - label_height)
        
        # Position text inside the background rectangle
        text_item.setPos(
            box_rect.left() + padding,
            box_rect.top() - label_height + padding
        )
        
        # Parent both to box so they move together
        bg_rect.setParentItem(box_item)
        text_item.setParentItem(box_item)
        
        # Store reference to text item on the box
        box_item.setData(0, text_item)
        box_item.setData(1, bg_rect)
        
        return text_item
    
    def update_box_label(self, box_item: QGraphicsRectItem):
        """
        Update the label position and font size for a box during resize.
        
        Args:
            box_item: The graphics rectangle item whose label needs updating
        """
        # Get existing label items
        text_item = box_item.data(0)  # Text item
        bg_rect = box_item.data(1)    # Background rectangle
        
        if not text_item or not bg_rect:
            return
        
        # Update font size based on new box height
        from PyQt6.QtGui import QFont
        font = QFont()
        box_height = box_item.rect().height()
        font_size = int(box_height / 15)
        font_size = max(7, min(font_size, 14))
        font.setPointSize(font_size)
        font.setBold(True)
        text_item.setFont(font)
        
        # Recalculate text dimensions
        text_rect = text_item.boundingRect()
        padding = 3
        
        # Update background size
        label_width = text_rect.width() + (padding * 2)
        label_height = text_rect.height() + (padding * 2)
        bg_rect.setRect(0, 0, label_width, label_height)
        
        # Update positions relative to box
        box_rect = box_item.rect()
        bg_rect.setPos(box_rect.left(), box_rect.top() - label_height)
        text_item.setPos(
            box_rect.left() + padding,
            box_rect.top() - label_height + padding
        )
    
    # ========================================================================
    # UNDO/REDO FUNCTIONALITY
    # ========================================================================
    
    def save_state(self):
        """Save current state for undo functionality."""
        # Create deep copy of current boxes
        state = []
        for bbox in self.boxes:
            new_bbox = BoundingBox(
                QRectF(bbox.rect),
                bbox.class_id,
                bbox.class_name
            )
            state.append(new_bbox)
        
        self.undo_stack.append(state)
        # Clear redo stack when new action is performed
        self.redo_stack.clear()
    
    def undo(self) -> bool:
        """
        Undo last action.
        
        Returns:
            True if undo was successful, False if nothing to undo
        """
        if not self.undo_stack:
            return False
        
        # Save current state to redo stack
        current_state = []
        for bbox in self.boxes:
            new_bbox = BoundingBox(
                QRectF(bbox.rect),
                bbox.class_id,
                bbox.class_name
            )
            current_state.append(new_bbox)
        self.redo_stack.append(current_state)
        
        # Restore previous state
        previous_state = self.undo_stack.pop()
        self.restore_state(previous_state)
        
        return True
    
    def redo(self) -> bool:
        """
        Redo last undone action.
        
        Returns:
            True if redo was successful, False if nothing to redo
        """
        if not self.redo_stack:
            return False
        
        # Save current state to undo stack
        current_state = []
        for bbox in self.boxes:
            new_bbox = BoundingBox(
                QRectF(bbox.rect),
                bbox.class_id,
                bbox.class_name
            )
            current_state.append(new_bbox)
        self.undo_stack.append(current_state)
        
        # Restore redo state
        redo_state = self.redo_stack.pop()
        self.restore_state(redo_state)
        
        return True
    
    def restore_state(self, state: List[BoundingBox]):
        """
        Restore scene to a previous state.
        
        Args:
            state: List of BoundingBox objects representing the state
        """
        # Clear current boxes
        for bbox in self.boxes:
            if bbox.graphics_item:
                self.removeItem(bbox.graphics_item)
        
        self.boxes.clear()
        self.selected_box = None
        
        # Restore boxes from state
        for bbox in state:
            # Create new graphics item
            new_item = QGraphicsRectItem(bbox.rect)
            color = self.get_box_color(bbox.class_id)
            pen = QPen(color, 3)  # Thicker pen
            new_item.setPen(pen)
            # No brush - outline only
            self.addItem(new_item)
            
            # Add label
            self.add_box_label(new_item, bbox.class_name, color)
            
            # Create new BoundingBox
            new_bbox = BoundingBox(
                QRectF(bbox.rect),
                bbox.class_id,
                bbox.class_name
            )
            new_bbox.graphics_item = new_item
            self.boxes.append(new_bbox)


# ============================================================================
# IMAGE VIEW CLASS
# ============================================================================

class ImageView(QGraphicsView):
    """
    Custom graphics view with zoom and pan capabilities.
    
    Features:
    - Scroll wheel zoom (with Ctrl modifier)
    - Smooth zooming with keyboard shortcuts
    - Pan with middle mouse button
    - Fit to window functionality
    """
    
    def __init__(self, scene: AnnotationScene, parent=None):
        """
        Initialize the image view.
        
        Args:
            scene: The AnnotationScene to display
            parent: Parent widget
        """
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        self.zoom_factor = 1.15
        self.current_zoom = 1.0
        self.panning = False
        self.pan_start = None
    
    def mousePressEvent(self, event):
        """Handle mouse press for panning with middle button."""
        if event.button() == Qt.MouseButton.MiddleButton:
            # Start panning with middle mouse button
            self.panning = True
            self.pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for panning."""
        if self.panning and self.pan_start:
            # Pan the view
            delta = event.pos() - self.pan_start
            self.pan_start = event.pos()
            
            # Update scroll bars
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            # Stop panning
            self.panning = False
            self.pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event: QWheelEvent):
        """
        Handle mouse wheel events for zooming.
        
        Hold Ctrl and scroll to zoom in/out.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom with Ctrl + Scroll
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            # Normal scroll
            super().wheelEvent(event)
    
    def zoom_in(self):
        """Zoom in by factor."""
        self.scale(self.zoom_factor, self.zoom_factor)
        self.current_zoom *= self.zoom_factor
    
    def zoom_out(self):
        """Zoom out by factor."""
        self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
        self.current_zoom /= self.zoom_factor
    
    def fit_in_view(self):
        """Fit the entire scene in the view."""
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.current_zoom = 1.0
    
    def reset_zoom(self):
        """Reset zoom to 100%."""
        self.resetTransform()
        self.current_zoom = 1.0


# ============================================================================
# MAIN WINDOW CLASS
# ============================================================================

class MainWindow(QMainWindow):
    """
    Main application window.
    
    Manages:
    - UI layout and widgets
    - File operations
    - Annotation workflow
    - Export functionality
    - Keyboard shortcuts
    
    Author: Ahmed Fekry
    LinkedIn: www.linkedin.com/in/ahmed-fekry07
    """
    
    def __init__(self):
        """Initialize the main window and set up the UI."""
        super().__init__()
        self.setWindowTitle("YOLO Annotator - Image Annotation Tool")
        self.setGeometry(100, 100, 1400, 900)
        
        # File paths and state
        self.image_files: List[Path] = []
        self.current_image_index: int = 0
        self.current_image_path: Optional[Path] = None
        self.image_directory: Optional[Path] = None
        self.labels_directory: Optional[Path] = None
        self.class_file_path: Optional[Path] = None
        self.unsaved_changes: bool = False
        
        # Classes management
        self.classes: List[str] = []  # For backwards compatibility and display
        self.class_id_map: dict = {}  # Maps class_id (int) -> class_name (str) - allows arbitrary IDs
        self.class_colors: dict = {}  # class_id -> QColor mapping
        
        # Setup UI components
        self.setup_ui()
        self.setup_menu()
        self.setup_shortcuts()
        self.setup_connections()
        
        # Set initial status
        self.statusBar().showMessage("Ready - Open an image or directory to start annotating")
    
    def setup_ui(self):
        """Set up the user interface layout."""
        # Create central scene and view
        self.scene = AnnotationScene()
        self.view = ImageView(self.scene)
        self.setCentralWidget(self.view)
        
        # ====================================================================
        # LEFT DOCK: FILE BROWSER
        # ====================================================================
        files_dock = QDockWidget("Files", self)
        files_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        files_widget = QWidget()
        files_layout = QVBoxLayout(files_widget)
        
        # Image files list
        self.files_list = QListWidget()
        self.files_list.itemDoubleClicked.connect(self.on_file_double_clicked)
        files_layout.addWidget(QLabel("Image Files:"))
        files_layout.addWidget(self.files_list)
        
        # Image info label
        self.info_label = QLabel("No image loaded")
        self.info_label.setWordWrap(True)
        files_layout.addWidget(self.info_label)
        
        files_dock.setWidget(files_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, files_dock)
        
        # ====================================================================
        # RIGHT DOCK: CLASSES
        # ====================================================================
        classes_dock = QDockWidget("Classes", self)
        classes_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        classes_widget = QWidget()
        classes_layout = QVBoxLayout(classes_widget)
        
        # Classes list
        self.classes_list = QListWidget()
        if self.classes:
            for i, cls in enumerate(self.classes):
                self.classes_list.addItem(f"[{i}] {cls}")
            self.classes_list.setCurrentRow(0)
        classes_layout.addWidget(QLabel("Annotation Classes:"))
        classes_layout.addWidget(self.classes_list)
        
        # Classes buttons
        btn_layout = QHBoxLayout()
        self.add_class_btn = QPushButton("Add Class")
        self.remove_class_btn = QPushButton("Remove Class")
        btn_layout.addWidget(self.add_class_btn)
        btn_layout.addWidget(self.remove_class_btn)
        classes_layout.addLayout(btn_layout)
        
        # Save classes button
        save_classes_layout = QHBoxLayout()
        self.save_classes_btn = QPushButton("Save Classes")
        self.save_classes_btn.clicked.connect(self.save_classes_file)
        save_classes_layout.addWidget(self.save_classes_btn)
        classes_layout.addLayout(save_classes_layout)
        
        classes_dock.setWidget(classes_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, classes_dock)
        
        # ====================================================================
        # RIGHT DOCK: ANNOTATIONS
        # ====================================================================
        annotations_dock = QDockWidget("Annotations", self)
        annotations_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | 
            Qt.DockWidgetArea.RightDockWidgetArea
        )
        annotations_widget = QWidget()
        annotations_layout = QVBoxLayout(annotations_widget)
        
        # Annotations list
        self.annotations_list = QListWidget()
        self.annotations_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        annotations_layout.addWidget(QLabel("Bounding Boxes:"))
        annotations_layout.addWidget(self.annotations_list)
        
        # Annotation control buttons
        control_layout = QHBoxLayout()
        
        self.select_btn = QPushButton("Select")
        self.select_btn.clicked.connect(self.toggle_selection)
        
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_selected_annotation)
        
        control_layout.addWidget(self.select_btn)
        control_layout.addWidget(self.edit_btn)
        annotations_layout.addLayout(control_layout)
        
        # Delete and Export buttons
        action_layout = QHBoxLayout()
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_selected_annotation)
        
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.export_selected_annotation)
        
        action_layout.addWidget(self.delete_btn)
        action_layout.addWidget(self.export_btn)
        annotations_layout.addLayout(action_layout)
        
        annotations_dock.setWidget(annotations_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, annotations_dock)
    
    def setup_menu(self):
        """Set up the application menu bar."""
        menubar = self.menuBar()
        
        # ====================================================================
        # FILE MENU
        # ====================================================================
        file_menu = menubar.addMenu("&File")
        
        # Open Image
        open_image_action = QAction("Open &Image...", self)
        open_image_action.setShortcut(QKeySequence("Ctrl+O"))
        open_image_action.triggered.connect(self.open_image)
        file_menu.addAction(open_image_action)
        
        # Open Directory
        open_dir_action = QAction("Open &Directory...", self)
        open_dir_action.setShortcut(QKeySequence("Ctrl+D"))
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)
        
        file_menu.addSeparator()
        
        # Save
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_annotations)
        file_menu.addAction(save_action)
        
        # Change Label Directory
        change_labels_dir_action = QAction("Change &Label Directory...", self)
        change_labels_dir_action.setShortcut(QKeySequence("Ctrl+L"))
        change_labels_dir_action.triggered.connect(self.change_labels_directory)
        file_menu.addAction(change_labels_dir_action)
        
        file_menu.addSeparator()
        
        # Next Image
        next_image_action = QAction("&Next Image", self)
        next_image_action.setShortcut(QKeySequence("D"))
        next_image_action.triggered.connect(self.next_image)
        file_menu.addAction(next_image_action)
        
        # Previous Image
        prev_image_action = QAction("&Previous Image", self)
        prev_image_action.setShortcut(QKeySequence("A"))
        prev_image_action.triggered.connect(self.previous_image)
        file_menu.addAction(prev_image_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # ====================================================================
        # VIEW MENU
        # ====================================================================
        view_menu = menubar.addMenu("&View")
        
        # Fit to Window
        fit_view_action = QAction("&Fit to Window", self)
        fit_view_action.setShortcut(QKeySequence("F"))
        fit_view_action.triggered.connect(self.view.fit_in_view)
        view_menu.addAction(fit_view_action)
        
        # Reset Zoom
        reset_zoom_action = QAction("&Reset Zoom", self)
        reset_zoom_action.setShortcut(QKeySequence("R"))
        reset_zoom_action.triggered.connect(self.view.reset_zoom)
        view_menu.addAction(reset_zoom_action)
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts for quick actions."""
        # Undo
        undo_action = QAction("Undo", self)
        undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        undo_action.triggered.connect(self.undo_action)
        self.addAction(undo_action)
        
        # Redo
        redo_action = QAction("Redo", self)
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_action.triggered.connect(self.redo_action)
        self.addAction(redo_action)
        
        # Delete
        delete_action = QAction("Delete", self)
        delete_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        delete_action.triggered.connect(self.delete_selected_annotation)
        self.addAction(delete_action)
        
        # Drawing mode toggle
        drawing_action = QAction("Toggle Drawing", self)
        drawing_action.setShortcut(QKeySequence("W"))
        drawing_action.triggered.connect(self.toggle_drawing_mode)
        self.addAction(drawing_action)
    
    def setup_connections(self):
        """Connect signals to slots."""
        self.classes_list.currentRowChanged.connect(self.on_class_changed)
        self.add_class_btn.clicked.connect(self.add_class)
        self.remove_class_btn.clicked.connect(self.remove_class)
        self.annotations_list.currentRowChanged.connect(self.on_annotation_selected)
        self.annotations_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.scene.box_created.connect(self.on_box_created)
        self.scene.box_selected.connect(self.on_box_selected_in_viewer)
    
    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================
    
    def undo_action(self):
        """Undo the last action."""
        if self.scene.undo():
            self.refresh_annotations_list()
            self.unsaved_changes = True
            self.statusBar().showMessage("Undo successful")
    
    def redo_action(self):
        """Redo the last undone action."""
        if self.scene.redo():
            self.refresh_annotations_list()
            self.unsaved_changes = True
            self.statusBar().showMessage("Redo successful")
    
    def toggle_drawing_mode(self):
        """Toggle between drawing and selection mode."""
        self.scene.drawing_enabled = not self.scene.drawing_enabled
        mode = "Drawing" if self.scene.drawing_enabled else "Selection"
        self.statusBar().showMessage(f"Mode: {mode}")
    
    def on_class_changed(self, index: int):
        """Handle class selection change."""
        # Get the sorted list of class IDs to find which one was selected
        sorted_ids = sorted(self.class_id_map.keys())
        if 0 <= index < len(sorted_ids):
            class_id = sorted_ids[index]
            class_name = self.class_id_map[class_id]
            # Get custom color if available
            color = self.class_colors.get(class_id, None)
            self.scene.set_current_class(class_id, class_name, color)
            self.statusBar().showMessage(f"Current class: [{class_id}] {class_name}")
    
    def on_box_created(self):
        """Handle new box creation."""
        self.refresh_annotations_list()
        self.unsaved_changes = True
    
    def on_annotation_selected(self, index: int):
        """Handle annotation selection from list."""
        pass  # Using on_selection_changed instead
    
    def on_selection_changed(self):
        """Handle selection changes in annotations list - sync with viewer."""
        # Get all selected indices
        selected_rows = self.annotations_list.selectedIndexes()
        selected_indices = set(idx.row() for idx in selected_rows)
        
        # Clear all highlights first
        for bbox in self.scene.boxes:
            if bbox.graphics_item:
                color = self.scene.get_box_color(bbox.class_id)
                pen = QPen(color, 3)  # Thicker pen
                bbox.graphics_item.setPen(pen)
        
        # Highlight all selected boxes
        for idx in selected_indices:
            if 0 <= idx < len(self.scene.boxes):
                bbox = self.scene.boxes[idx]
                if bbox.graphics_item:
                    pen = QPen(QColor(255, 255, 255), 4)  # White highlight, extra thick
                    bbox.graphics_item.setPen(pen)
    
    def on_box_selected_in_viewer(self, bbox: BoundingBox):
        """Handle box selection from viewer - sync with annotations list."""
        # Find the index of this box
        for i, b in enumerate(self.scene.boxes):
            if b == bbox:
                # Highlight this item in the annotations list
                self.annotations_list.setCurrentRow(i)
                break
    
    def on_file_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on file in list."""
        index = self.files_list.row(item)
        if 0 <= index < len(self.image_files):
            self.current_image_index = index
            self.load_image(self.image_files[index])
    
    def refresh_annotations_list(self):
        """Update the annotations list widget."""
        self.annotations_list.clear()
        for i, bbox in enumerate(self.scene.boxes):
            item_text = f"[{i}] {bbox.class_name} (class {bbox.class_id})"
            self.annotations_list.addItem(item_text)
    
    # ========================================================================
    # CLASS MANAGEMENT
    # ========================================================================
    
    def add_class(self):
        """Add a new annotation class with custom color."""
        from PyQt6.QtWidgets import QColorDialog
        
        # Get class name
        class_name, ok = QInputDialog.getText(
            self, "Add Class",
            "Enter class name:"
        )
        
        if not ok or not class_name:
            return
        
        class_name = class_name.strip()
        
        # Check if class already exists
        if class_name in self.class_id_map.values():
            QMessageBox.warning(
                self, "Duplicate Class",
                f"Class '{class_name}' already exists."
            )
            return
        
        # Get class ID - suggest next available ID
        default_id = max(self.class_id_map.keys()) + 1 if self.class_id_map else 0
        class_id, ok = QInputDialog.getInt(
            self, "Class ID",
            f"Enter class ID for '{class_name}':",
            default_id, 0, 999
        )
        
        if not ok:
            return
        
        # Get custom color
        color = QColorDialog.getColor(
            initial=QColor(0, 255, 0),  # Default green
            parent=self,
            title=f"Choose color for '{class_name}'"
        )
        
        if not color.isValid():
            # User cancelled color selection - use default
            color = self.scene.get_box_color(class_id)
        
        # Add class to the ID map (allows arbitrary IDs)
        self.class_id_map[class_id] = class_name
        
        # Update classes list for backwards compatibility
        # We'll rebuild it sorted by class_id for display
        sorted_ids = sorted(self.class_id_map.keys())
        self.classes = [self.class_id_map[cid] for cid in sorted_ids]
        
        # Store custom color
        self.class_colors[class_id] = color
        self.scene.set_class_color(class_id, color)
        
        # Refresh classes list display with actual class IDs
        self.classes_list.clear()
        for cid in sorted_ids:
            self.classes_list.addItem(f"[{cid}] {self.class_id_map[cid]}")
        
        self.statusBar().showMessage(f"Added class: {class_name} with ID {class_id}")
    
    def remove_class(self):
        """Remove selected annotation class."""
        current_row = self.classes_list.currentRow()
        
        # Get sorted class IDs to find which one is selected
        sorted_ids = sorted(self.class_id_map.keys())
        if current_row < 0 or current_row >= len(sorted_ids):
            QMessageBox.information(
                self, "No Selection",
                "Please select a class to remove."
            )
            return
        
        class_id = sorted_ids[current_row]
        class_name = self.class_id_map[class_id]
        
        # Check if class is in use
        in_use = any(bbox.class_id == class_id for bbox in self.scene.boxes)
        
        if in_use:
            reply = QMessageBox.question(
                self, "Class In Use",
                f"Class '{class_name}' is being used by annotations.\n"
                f"Removing it will also remove all boxes with this class.\n\n"
                f"Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            # Remove boxes with this class
            indices_to_remove = [
                i for i, bbox in enumerate(self.scene.boxes)
                if bbox.class_id == class_id
            ]
            
            if indices_to_remove:
                self.scene.delete_selected_boxes(indices_to_remove)
        
        # Remove class from map
        del self.class_id_map[class_id]
        
        # Rebuild classes list
        sorted_ids = sorted(self.class_id_map.keys())
        self.classes = [self.class_id_map[cid] for cid in sorted_ids]
        
        # Note: We don't update class IDs of other boxes since IDs can be arbitrary
        
        # Refresh UI
        self.classes_list.clear()
        for cid in sorted_ids:
            self.classes_list.addItem(f"[{cid}] {self.class_id_map[cid]}")
        
        # Select first class if any remain
        if self.classes:
            self.classes_list.setCurrentRow(0)
        
        # Refresh display
        self.refresh_annotations_list()
        self.unsaved_changes = True
        self.statusBar().showMessage(f"Removed class: {class_name}")
    
    def save_classes(self):
        """Internal method - Save classes to file if path is set."""
        if not self.class_file_path:
            return
        
        try:
            with open(self.class_file_path, 'w') as f:
                for class_name in self.classes:
                    f.write(class_name + '\n')
        except Exception as e:
            QMessageBox.warning(
                self, "Warning",
                f"Failed to save classes: {str(e)}"
            )
    
    def save_classes_file(self):
        """Save classes file with user-chosen location."""
        if not self.classes:
            QMessageBox.information(
                self, "No Classes",
                "Please add at least one class before saving."
            )
            return
        
        # Suggest default location
        default_dir = str(self.labels_directory) if self.labels_directory else ""
        if not default_dir and self.image_directory:
            default_dir = str(self.image_directory)
        
        default_path = Path(default_dir) / "classes.txt" if default_dir else "classes.txt"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Classes File",
            str(default_path),
            "Text Files (*.txt);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w') as f:
                for i, class_name in enumerate(self.classes):
                    f.write(f"[{i}] {class_name}\n")
            
            # Update class file path
            self.class_file_path = Path(file_path)
            
            QMessageBox.information(
                self, "Classes Saved",
                f"Classes saved successfully!\n\n"
                f"File: {Path(file_path).name}\n"
                f"Location: {Path(file_path).parent}\n"
                f"Classes: {len(self.classes)}\n\n"
                f"Format: [ID] ClassName (one per line)"
            )
            
            self.statusBar().showMessage(f"Saved {len(self.classes)} classes to {Path(file_path).name}")
            
        except Exception as e:
            QMessageBox.critical(
                self, "Save Error",
                f"Failed to save classes file: {str(e)}"
            )
    
    def load_classes(self):
        """Load classes from classes.txt file."""
        if not self.class_file_path or not self.class_file_path.exists():
            return
        
        try:
            with open(self.class_file_path, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Clear existing classes
            self.classes = []
            self.class_id_map = {}
            
            # Parse each line - could be just name or "[id] name"
            for i, line in enumerate(lines):
                if line.startswith('[') and ']' in line:
                    # Format: [id] name
                    bracket_end = line.index(']')
                    class_id = int(line[1:bracket_end])
                    class_name = line[bracket_end+1:].strip()
                else:
                    # Format: just name (use sequential ID)
                    class_id = i
                    class_name = line
                
                self.class_id_map[class_id] = class_name
            
            # Rebuild classes list sorted by ID
            sorted_ids = sorted(self.class_id_map.keys())
            self.classes = [self.class_id_map[cid] for cid in sorted_ids]
            
            # Refresh classes list display
            self.classes_list.clear()
            for cid in sorted_ids:
                self.classes_list.addItem(f"[{cid}] {self.class_id_map[cid]}")
            
            if self.classes:
                self.classes_list.setCurrentRow(0)
                
        except Exception as e:
            QMessageBox.warning(
                self, "Warning",
                f"Failed to load classes: {str(e)}"
            )
    
    # ========================================================================
    # ANNOTATION OPERATIONS
    # ========================================================================
    
    def toggle_selection(self):
        """Toggle selection of all annotations."""
        if self.annotations_list.count() == 0:
            return
        
        # Check if all are selected
        selected_count = len(self.annotations_list.selectedIndexes())
        total_count = self.annotations_list.count()
        
        if selected_count == total_count:
            # Deselect all
            self.annotations_list.clearSelection()
        else:
            # Select all
            self.annotations_list.selectAll()
    
    def edit_selected_annotation(self):
        """Enable editing mode for selected annotation."""
        selected_rows = self.annotations_list.selectedIndexes()
        
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection",
                "Please select an annotation to edit."
            )
            return
        
        # Only edit the first selected annotation
        row = selected_rows[0].row()
        
        if 0 <= row < len(self.scene.boxes):
            bbox = self.scene.boxes[row]
            
            # Enable editing mode for this box
            if bbox.graphics_item:
                # Make item movable
                bbox.graphics_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
                bbox.graphics_item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
                
                # Highlight with thicker border
                pen = QPen(QColor(255, 255, 0), 4)  # Yellow thick border
                bbox.graphics_item.setPen(pen)
                
                # Mark as being edited
                self.scene.editing_box = bbox
                
                # Add resize handles
                self.scene.add_resize_handles(bbox)
                
                self.statusBar().showMessage(
                    "Edit mode: Drag box to move, drag handles to resize"
                )
    
    def delete_selected_annotation(self):
        """Delete the selected annotation(s)."""
        selected_rows = self.annotations_list.selectedIndexes()
        
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection",
                "Please select annotation(s) to delete."
            )
            return
        
        # Get unique row indices
        indices = sorted(set(index.row() for index in selected_rows), reverse=True)
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Delete {len(indices)} annotation(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.scene.delete_selected_boxes(indices)
            self.refresh_annotations_list()
            self.unsaved_changes = True
            self.statusBar().showMessage(f"Deleted {len(indices)} annotation(s)")
    
    def export_selected_annotation(self):
        """Export annotations to YOLO format file."""
        if not self.current_image_path:
            QMessageBox.warning(self, "No Image", "No image is currently loaded.")
            return
        
        # FIRST TIME ONLY: Ask user to choose directory
        if not self.labels_directory:
            QMessageBox.information(
                self, "Choose Labels Directory",
                "Please choose a directory where all your labels will be saved.\n\n"
                "This will be used for all future exports in this session.\n"
                "You can change it later with: File > Change Label Directory (Ctrl+L)"
            )
            
            self.set_labels_directory()
            
            # If user cancelled, abort export
            if not self.labels_directory:
                return
        
        # Create labels directory if it doesn't exist
        try:
            self.labels_directory.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self, "Directory Error",
                f"Failed to create labels directory: {str(e)}\n\nPath: {self.labels_directory}"
            )
            return
        
        # Determine which annotations to export
        selected_rows = self.annotations_list.selectedIndexes()
        
        if not selected_rows:
            # No selection - export all annotations
            boxes_to_export = list(range(len(self.scene.boxes)))
        else:
            # Export only selected annotations
            boxes_to_export = sorted(set(index.row() for index in selected_rows))
        
        if not boxes_to_export or not self.scene.boxes:
            QMessageBox.information(
                self, "Nothing to Export",
                "No annotations available to export."
            )
            return
        
        annotation_path = self.labels_directory / f"{self.current_image_path.stem}.txt"
        
        try:
            # Write annotations to file
            with open(annotation_path, 'w') as f:
                for i in boxes_to_export:
                    if i < len(self.scene.boxes):
                        bbox = self.scene.boxes[i]
                        yolo_line = bbox.to_yolo_format(
                            self.scene.image_width,
                            self.scene.image_height
                        )
                        f.write(yolo_line + '\n')
            
            # Silent success - just update status bar
            self.statusBar().showMessage(
                f"Exported {len(boxes_to_export)} annotation(s) → {self.labels_directory.name}/"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Failed to export annotations: {str(e)}\n\nPath: {annotation_path}"
            )
    
    # ========================================================================
    # FILE OPERATIONS
    # ========================================================================
    
    def open_image(self):
        """Open a single image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.pbm *.tif *.tiff);;All Files (*)"
        )
        
        if file_path:
            image_path = Path(file_path)
            self.image_directory = image_path.parent
            self.image_files = [image_path]
            self.current_image_index = 0
            self.load_image(image_path)
    
    def open_directory(self):
        """Open a directory containing images."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Image Directory"
        )
        
        if dir_path:
            directory = Path(dir_path)
            self.image_directory = directory
            self.load_image_directory(directory)
            
            # Load classes if available
            classes_file = directory / "classes.txt"
            if classes_file.exists():
                self.class_file_path = classes_file
                self.load_classes()
    
    def load_image_directory(self, directory: Path):
        """Load all images from a directory."""
        # Find all image files - use set to avoid duplicates
        extensions = [
            '*.png', '*.jpg', '*.jpeg', '*.bmp', '*.pbm', '*.tif', '*.tiff',
            '*.PNG', '*.JPG', '*.JPEG', '*.BMP', '*.PBM', '*.TIF', '*.TIFF'
        ]
        image_files_set = set()
        for ext in extensions:
            for file in directory.glob(ext):
                image_files_set.add(file)
        
        self.image_files = sorted(list(image_files_set))
        
        if not self.image_files:
            QMessageBox.warning(
                self, "No Images",
                f"No image files found in: {directory}"
            )
            return
        
        # Update files list
        self.files_list.clear()
        for img_file in self.image_files:
            self.files_list.addItem(img_file.name)
        
        # Load first image
        self.current_image_index = 0
        self.load_image(self.image_files[0])
        
        self.statusBar().showMessage(f"Loaded {len(self.image_files)} images from {directory.name}")
    
    def load_image(self, image_path: Path):
        """Load and display an image."""
        # Ask user if they want to save current annotations before switching
        if self.current_image_path and len(self.scene.boxes) > 0:
            reply = QMessageBox.question(
                self, "Save Annotations?",
                f"You have {len(self.scene.boxes)} annotation(s) on the current image.\n\n"
                f"Do you want to export them before loading the new image?",
                QMessageBox.StandardButton.Yes | 
                QMessageBox.StandardButton.No | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                # User cancelled - don't load new image
                return
            elif reply == QMessageBox.StandardButton.Yes:
                # User wants to save - prompt for export
                self.export_current_annotations()
        
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            QMessageBox.critical(
                self, "Error",
                f"Failed to load image: {image_path}"
            )
            return
        
        self.current_image_path = image_path
        self.scene.set_image(pixmap)
        self.view.fit_in_view()
        
        # Clear annotations list for new image
        self.annotations_list.clear()
        
        # Load existing annotations if available
        self.load_annotations()
        
        # Reset unsaved changes flag
        self.unsaved_changes = False
        
        # Update info
        self.update_info_label()
        
        # Update file list selection
        if self.image_files:
            for i, img_file in enumerate(self.image_files):
                if img_file == image_path:
                    self.files_list.setCurrentRow(i)
                    break
        
        # Update status
        if self.image_files:
            status = f"Image {self.current_image_index + 1}/{len(self.image_files)}: {image_path.name}"
        else:
            status = f"Loaded: {image_path.name}"
        self.statusBar().showMessage(status)
    
    def update_info_label(self):
        """Update the image info label."""
        if self.current_image_path:
            pixmap = QPixmap(str(self.current_image_path))
            info = f"Image: {self.current_image_path.name}\n"
            info += f"Size: {pixmap.width()} × {pixmap.height()}"
            self.info_label.setText(info)
        else:
            self.info_label.setText("No image loaded")
    
    def next_image(self):
        """Load the next image in the directory."""
        if not self.image_files:
            return
        
        self.current_image_index = (self.current_image_index + 1) % len(self.image_files)
        self.load_image(self.image_files[self.current_image_index])
    
    def previous_image(self):
        """Load the previous image in the directory."""
        if not self.image_files:
            return
        
        self.current_image_index = (self.current_image_index - 1) % len(self.image_files)
        self.load_image(self.image_files[self.current_image_index])
    
    # ========================================================================
    # SAVE/LOAD ANNOTATIONS
    # ========================================================================
    
    def save_annotations(self):
        """Save annotations in YOLO format."""
        if not self.current_image_path:
            return
        
        # Determine where to save the label file
        if self.labels_directory:
            # Create labels directory if it doesn't exist
            try:
                self.labels_directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self, "Directory Error",
                    f"Failed to create labels directory: {str(e)}\n\nPath: {self.labels_directory}"
                )
                return
            
            # Save to custom labels directory
            annotation_path = self.labels_directory / f"{self.current_image_path.stem}.txt"
        else:
            # Save next to image file (default behavior)
            annotation_path = self.current_image_path.with_suffix('.txt')
        
        if not self.scene.boxes:
            # If no boxes, create empty file or delete existing one
            if annotation_path.exists():
                annotation_path.unlink()
            self.unsaved_changes = False
            return
        
        try:
            with open(annotation_path, 'w') as f:
                for bbox in self.scene.boxes:
                    yolo_line = bbox.to_yolo_format(
                        self.scene.image_width,
                        self.scene.image_height
                    )
                    f.write(yolo_line + '\n')
            
            self.unsaved_changes = False
            self.statusBar().showMessage(f"Saved annotations: {annotation_path.name} -> {annotation_path.parent.name}/")
        except Exception as e:
            QMessageBox.critical(
                self, "Error",
                f"Failed to save annotations: {str(e)}\n\nPath: {annotation_path}"
            )
    
    def load_annotations(self):
        """Load existing annotations from YOLO format file automatically."""
        if not self.current_image_path:
            return
        
        # Try labels directory first, then image directory
        if self.labels_directory:
            annotation_path = self.labels_directory / f"{self.current_image_path.stem}.txt"
        else:
            annotation_path = self.current_image_path.with_suffix('.txt')
        
        if not annotation_path.exists():
            self.refresh_annotations_list()
            return
        
        try:
            with open(annotation_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    
                    class_id = int(parts[0])
                    
                    # Get class name from the map
                    if class_id in self.class_id_map:
                        class_name = self.class_id_map[class_id]
                    else:
                        class_name = f"class_{class_id}"
                    
                    # Parse YOLO format
                    bbox = BoundingBox.from_yolo_format(
                        line,
                        self.scene.image_width,
                        self.scene.image_height,
                        class_name
                    )
                    
                    if bbox:
                        # Create graphics item
                        item = QGraphicsRectItem(bbox.rect)
                        color = self.scene.get_box_color(bbox.class_id)
                        pen = QPen(color, 2)
                        item.setPen(pen)
                        # No brush - outline only
                        self.scene.addItem(item)
                        
                        # Add label
                        self.scene.add_box_label(item, bbox.class_name, color)
                        
                        bbox.graphics_item = item
                        self.scene.boxes.append(bbox)
            
            self.refresh_annotations_list()
            self.statusBar().showMessage(f"Loaded {len(self.scene.boxes)} annotation(s) from {annotation_path.name}")
            
        except Exception as e:
            QMessageBox.warning(
                self, "Warning",
                f"Failed to load annotations: {str(e)}"
            )
    
    def set_labels_directory(self):
        """Internal method - set labels directory."""
        current_dir = str(self.labels_directory) if self.labels_directory else ""
        if not current_dir and self.image_directory:
            current_dir = str(self.image_directory)
        
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Choose Labels Directory",
            current_dir
        )
        
        if dir_path:
            self.labels_directory = Path(dir_path)
            
            # Also save/move classes.txt to labels directory
            if self.class_file_path:
                new_class_file_path = self.labels_directory / "classes.txt"
                
                # Copy existing classes.txt if it exists
                if self.class_file_path.exists() and self.class_file_path != new_class_file_path:
                    import shutil
                    shutil.copy2(self.class_file_path, new_class_file_path)
                
                self.class_file_path = new_class_file_path
                self.save_classes()
            
            self.statusBar().showMessage(f"Labels will be saved to: {self.labels_directory}")
    
    def change_labels_directory(self):
        """Change the labels save directory (user-initiated)."""
        self.set_labels_directory()
    
    def export_current_annotations(self):
        """Export current annotations with user choosing location."""
        if not self.current_image_path:
            return
        
        if not self.scene.boxes:
            QMessageBox.information(
                self, "No Annotations",
                "There are no annotations to export."
            )
            return
        
        # Ask user where to save
        default_name = f"{self.current_image_path.stem}.txt"
        if self.labels_directory:
            default_path = self.labels_directory / default_name
        else:
            default_path = self.current_image_path.parent / default_name
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Annotations",
            str(default_path),
            "Text Files (*.txt);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Write annotations to file
            with open(file_path, 'w') as f:
                for bbox in self.scene.boxes:
                    yolo_line = bbox.to_yolo_format(
                        self.scene.image_width,
                        self.scene.image_height
                    )
                    f.write(yolo_line + '\n')
            
            # Update labels directory to the parent of saved file
            self.labels_directory = Path(file_path).parent
            
            self.statusBar().showMessage(
                f"Exported {len(self.scene.boxes)} annotation(s) to {Path(file_path).name}"
            )
            
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Failed to export annotations: {str(e)}"
            )
    
    # ========================================================================
    # APPLICATION LIFECYCLE
    # ========================================================================
    
    def closeEvent(self, event):
        """Handle application close."""
        # Don't prompt to save - user must explicitly export
        # This is consistent with the workflow where Export is the only save method
        event.accept()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """
    Application entry point.
    
    Author: Ahmed Fekry
    LinkedIn: www.linkedin.com/in/ahmed-fekry07
    """
    app = QApplication(sys.argv)
    app.setApplicationName("YOLO Annotator")
    app.setOrganizationName("Ahmed Fekry")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
